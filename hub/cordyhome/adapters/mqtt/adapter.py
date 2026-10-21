"""Adaptador dos aparelhos MQTT.

Diferente da Tuya, aqui não se pergunta nada ao aparelho: ele publica o estado sozinho e o
serviço MQTT guarda a última mensagem de cada tópico. Ler é consultar essa memória; mandar
um comando é publicar no tópico de comando do aparelho.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..base import BRIGHTNESS, AdapterError, DeviceReading, DeviceRef
from .discovery import Entity
from .template import parse_json, render


@dataclass
class Message:
    payload: str
    ts: float


class MqttConnection(Protocol):
    connected: bool
    messages: dict[str, Message]

    async def publish(self, topic: str, payload: str, qos: int = 0) -> None: ...


def device_entities(config: dict[str, Any]) -> tuple[Entity | None, list[Entity]]:
    control = Entity.from_dict(config["control"]) if config.get("control") else None
    sensors = [Entity.from_dict(s) for s in config.get("sensors") or []]
    return control, sensors


class MqttAdapter:
    name = "mqtt"

    def __init__(self, connection: MqttConnection):
        self.connection = connection
        # Estado suposto de aparelhos que não publicam o próprio estado.
        self._assumed: dict[int, bool] = {}

    def capabilities(self, config: dict[str, Any]) -> list[str]:
        return list(config.get("capabilities") or [])

    async def read(self, device: DeviceRef) -> DeviceReading:
        if not self.connection.connected:
            raise AdapterError("Sem conexão com o servidor MQTT.")
        control, sensors = device_entities(device.config)
        entities = [e for e in (control, *sensors) if e]
        available = _availability(entities, self.connection.messages)
        if available is False:
            raise AdapterError("O aparelho avisou que está desconectado.")
        reading = DeviceReading(online=True)
        heard = available is True
        if control:
            heard |= self._read_control(device, control, reading)
        for sensor in sensors:
            heard |= self._read_sensor(sensor, reading)
        if not heard:
            raise AdapterError("Ainda sem notícias do aparelho pelo MQTT.")
        return reading

    def _read_control(self, device: DeviceRef, entity: Entity, reading: DeviceReading) -> bool:
        message = self.connection.messages.get(entity.state_topic or "")
        if message is None:
            if device.id in self._assumed:
                reading.is_on = self._assumed[device.id]
            return False
        if entity.schema == "json":
            data = parse_json(message.payload)
            if isinstance(data, dict):
                state = str(data.get("state", "")).upper()
                reading.is_on = {"ON": True, "OFF": False}.get(state)
                if entity.brightness and isinstance(data.get("brightness"), int | float):
                    reading.state[BRIGHTNESS] = _to_percent(data["brightness"], entity)
            return True
        value = render(entity.value_template, message.payload)
        if value == entity.state_on:
            reading.is_on = True
        elif value == entity.state_off:
            reading.is_on = False
        bright = self.connection.messages.get(entity.brightness_state_topic or "")
        if bright is not None:
            raw = _number(render(entity.brightness_value_template, bright.payload))
            if raw is not None:
                reading.state[BRIGHTNESS] = _to_percent(raw, entity)
        return True

    def _read_sensor(self, entity: Entity, reading: DeviceReading) -> bool:
        message = self.connection.messages.get(entity.state_topic or "")
        if message is None:
            return False
        value = _number(render(entity.value_template, message.payload))
        if value is None:
            return True
        unit = (entity.unit or "").lower()
        if entity.device_class == "power":
            reading.power_w = value * 1000 if unit == "kw" else value
        elif entity.device_class == "voltage":
            reading.voltage_v = value / 1000 if unit == "mv" else value
        elif entity.device_class == "current":
            reading.current_a = value / 1000 if unit == "ma" else value
        return True

    async def set_power(self, device: DeviceRef, on: bool) -> DeviceReading | None:
        control, _ = device_entities(device.config)
        if control is None or not control.command_topic:
            raise AdapterError("Este aparelho só mede; não dá para ligar ou desligar.")
        if control.schema == "json":
            payload = json.dumps({"state": "ON" if on else "OFF"})
        else:
            payload = control.payload_on if on else control.payload_off
            if control.command_template:
                rendered = render(control.command_template, payload)
                if rendered is None:
                    raise AdapterError("O modelo de comando do aparelho não funcionou.")
                payload = rendered
        await self._publish(control.command_topic, payload, control.qos)
        if not control.state_topic:
            self._assumed[device.id] = on
        return DeviceReading(online=True, is_on=on)

    async def set_state(self, device: DeviceRef, changes: dict[str, Any]) -> DeviceReading | None:
        control, _ = device_entities(device.config)
        if control is None or BRIGHTNESS not in changes or set(changes) - {BRIGHTNESS}:
            raise AdapterError("Este aparelho não aceita esse ajuste.")
        raw = round(changes[BRIGHTNESS] * control.brightness_scale / 100)
        if control.schema == "json":
            await self._publish(
                control.command_topic or "",
                json.dumps({"state": "ON", "brightness": raw}),
                control.qos,
            )
        elif control.brightness_command_topic:
            await self._publish(control.brightness_command_topic, str(raw), control.qos)
        else:
            raise AdapterError("Este aparelho não aceita ajuste de brilho.")
        return DeviceReading(online=True, is_on=True, state={BRIGHTNESS: changes[BRIGHTNESS]})

    async def _publish(self, topic: str, payload: str, qos: int) -> None:
        if not self.connection.connected:
            raise AdapterError("Sem conexão com o servidor MQTT.")
        try:
            await self.connection.publish(topic, payload, qos)
        except Exception as exc:  # noqa: BLE001 - qualquer falha do cliente vira erro legível
            raise AdapterError(f"Não consegui enviar o comando pelo MQTT: {exc}") from exc

    def forget(self, device_id: int) -> None:
        self._assumed.pop(device_id, None)


def _availability(entities: list[Entity], messages: dict[str, Message]) -> bool | None:
    """True/False quando o aparelho informa se está conectado; None se não informa."""
    results: list[tuple[float, bool]] = []
    seen: set[str] = set()
    for entity in entities:
        for item in entity.availability:
            message = messages.get(item.topic)
            if item.topic in seen or message is None:
                continue
            seen.add(item.topic)
            value = render(item.value_template, message.payload)
            if value == item.payload_available:
                results.append((message.ts, True))
            elif value == item.payload_not_available:
                results.append((message.ts, False))
    if not results:
        return None
    mode = entities[0].availability_mode if entities else "latest"
    if mode == "all":
        return all(ok for _, ok in results)
    if mode == "any":
        return any(ok for _, ok in results)
    return max(results)[1]


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_percent(raw: float, entity: Entity) -> int:
    return max(1, min(100, round(raw * 100 / entity.brightness_scale)))
