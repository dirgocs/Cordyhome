"""Controle local de dispositivos Tuya via tinytuya (sem nuvem)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import tinytuya

from ..base import AdapterError, DeviceReading, DeviceRef
from .dps import DpMap, parse_dps

log = logging.getLogger(__name__)

PROTOCOL_VERSIONS = (3.3, 3.4, 3.5, 3.1)

# Muitas tomadas só recalculam potência, tensão e corrente quando recebem o pedido UPDATEDPS;
# sem ele a leitura fica parada (em 0 W, por exemplo). Esperamos a resposta por pouco tempo e,
# se a tomada nunca responde, voltamos a só mandar o pedido sem esperar.
UPDATE_TIMEOUT = 1.5
UPDATE_MISSES_LIMIT = 3

# Códigos de erro do tinytuya que indicam chave/versão erradas (e não falta de rede).
_KEY_OR_VERSION_ERRORS = {"904", "914"}
_NETWORK_ERRORS = {"901", "902", "905"}


def _error_message(code: str | None) -> str:
    if code in _KEY_OR_VERSION_ERRORS:
        return "Chave local ou versão de protocolo incorreta. A tomada foi pareada de novo no app?"
    if code in _NETWORK_ERRORS:
        return "Sem resposta na rede. Verifique se a tomada está energizada e no Wi-Fi."
    return f"Erro de comunicação Tuya ({code or 'desconhecido'})."


class TuyaLocalAdapter:
    name = "tuya"

    def __init__(self, timeout: float = 4.0):
        self.timeout = timeout
        self._devices: dict[int, tinytuya.Device] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._update_misses: dict[int, int] = {}

    def forget(self, device_id: int) -> None:
        self._update_misses.pop(device_id, None)
        dev = self._devices.pop(device_id, None)
        if dev is not None:
            with contextlib.suppress(Exception):  # fechar socket é best effort
                dev.close()

    def _lock(self, device_id: int) -> asyncio.Lock:
        return self._locks.setdefault(device_id, asyncio.Lock())

    def _device(self, ref: DeviceRef, version: float) -> tinytuya.Device:
        cfg = ref.config
        dev = self._devices.get(ref.id)
        if dev is None or getattr(dev, "version", None) != version:
            dev = tinytuya.OutletDevice(
                dev_id=ref.external_id,
                address=cfg["ip"],
                local_key=cfg["local_key"],
                version=version,
                connection_timeout=self.timeout,
                connection_retry_limit=1,
                connection_retry_delay=1,
            )
            dev.set_socketTimeout(self.timeout)
            self._devices[ref.id] = dev
        return dev

    async def read(self, device: DeviceRef) -> DeviceReading:
        mapping = DpMap.from_dict(device.config.get("dp_map"))

        def op(dev: tinytuya.Device) -> dict[str, Any]:
            fresh = self._refresh_energy(device.id, dev, mapping.energy_dps)
            result = dev.status()
            if fresh and isinstance(result, dict) and "Err" not in result:
                # Os valores recalculados valem mais que os da consulta, que podem estar parados.
                result = {**result, "dps": {**(result.get("dps") or {}), **fresh}}
            return result

        result, version = await self._run(device, op)
        values = parse_dps(result.get("dps") or {}, mapping)
        raw: dict[str, Any] = {"dps": result.get("dps")}
        if version != _configured_version(device):
            raw["detected_version"] = version
        return DeviceReading(online=True, raw=raw, **values)

    def _refresh_energy(self, device_id: int, dev: tinytuya.Device, dps: list[int]) -> dict:
        """Pede à tomada que recalcule a medição e devolve os valores novos que ela mandar."""
        if not dps:
            return {}
        wanted = {str(dp) for dp in dps}
        if self._update_misses.get(device_id, 0) >= UPDATE_MISSES_LIMIT:
            with contextlib.suppress(Exception):  # firmwares antigos não suportam
                dev.updatedps(dps, nowait=True)
            return {}
        reply = None
        try:
            dev.set_socketTimeout(UPDATE_TIMEOUT)
            reply = dev.updatedps(dps)
        except Exception as exc:  # noqa: BLE001 - tinytuya levanta tipos variados
            log.debug("tuya updatedps: %s", exc)
        finally:
            with contextlib.suppress(Exception):
                dev.set_socketTimeout(self.timeout)
        values = reply.get("dps") if isinstance(reply, dict) else None
        fresh = {k: v for k, v in (values or {}).items() if str(k) in wanted}
        if fresh:
            self._update_misses[device_id] = 0
        else:
            self._update_misses[device_id] = self._update_misses.get(device_id, 0) + 1
        return {str(k): v for k, v in fresh.items()}

    async def set_power(self, device: DeviceRef, on: bool) -> DeviceReading | None:
        mapping = DpMap.from_dict(device.config.get("dp_map"))
        result, _ = await self._run(device, lambda dev: dev.set_status(on, switch=mapping.switch))
        dps = result.get("dps") or {}
        values = parse_dps(dps, mapping)
        if "is_on" not in values:
            values["is_on"] = on
        return DeviceReading(online=True, raw={"dps": dps}, **values)

    def capabilities(self, config: dict[str, Any]) -> list[str]:
        return DpMap.from_dict(config.get("dp_map")).capabilities

    async def set_state(self, device: DeviceRef, changes: dict[str, Any]) -> DeviceReading | None:
        mapping = DpMap.from_dict(device.config.get("dp_map"))
        dps = mapping.state_dps(changes)
        result, _ = await self._run(device, lambda dev: dev.set_multiple_values(dps))
        values = parse_dps(result.get("dps") or {}, mapping)
        # A resposta pode trazer só parte dos DPs: o que foi pedido vale até a próxima leitura.
        values.setdefault("is_on", True)
        values["state"] = {**changes, **values.get("state", {})}
        return DeviceReading(online=True, raw={"dps": result.get("dps")}, **values)

    async def _run(self, device: DeviceRef, op) -> tuple[dict[str, Any], float]:
        cfg = device.config
        if not cfg.get("ip"):
            raise AdapterError("Endereço IP desconhecido. Rode a busca de dispositivos na rede.")
        if not cfg.get("local_key"):
            raise AdapterError("Chave local ausente. Sincronize a conta Tuya novamente.")

        configured = _configured_version(device)
        # Versão confirmada: só ela. Caso contrário, tenta as versões conhecidas em ordem.
        candidates = (
            [configured]
            if cfg.get("version_confirmed")
            else [configured, *[v for v in PROTOCOL_VERSIONS if v != configured]]
        )
        async with self._lock(device.id):
            last_code: str | None = None
            for version in candidates:
                dev = self._device(device, version)
                try:
                    result = await asyncio.to_thread(op, dev)
                except Exception as exc:  # noqa: BLE001 - tinytuya levanta tipos variados
                    log.debug("tuya %s: %s", device.external_id, exc)
                    self.forget(device.id)
                    raise AdapterError("Falha de comunicação com a tomada.") from exc
                if not isinstance(result, dict):
                    raise AdapterError("Resposta inesperada da tomada.")
                code = str(result.get("Err")) if "Err" in result else None
                if code is None:
                    return result, version
                last_code = code
                self.forget(device.id)
                if code not in _KEY_OR_VERSION_ERRORS:
                    break
            raise AdapterError(_error_message(last_code))


def _configured_version(device: DeviceRef) -> float:
    try:
        return float(device.config.get("version") or 3.3)
    except (TypeError, ValueError):
        return 3.3
