from __future__ import annotations

import asyncio
import json
import socket

import pytest
from amqtt.client import ConnectError, MQTTClient

from cordyhome.adapters.base import AdapterError, DeviceRef
from cordyhome.adapters.mqtt.adapter import Message, MqttAdapter
from cordyhome.adapters.mqtt.discovery import group_candidates, parse_discovery
from cordyhome.adapters.mqtt.template import render

PREFIX = "homeassistant"
DEVICE = {"ids": ["1gsp-a1b2c3"], "name": "MINI-1GSP", "mf": "SONOFF", "mdl": "MINI ONE PM"}

# Descoberta no estilo de um relé com medição (como o SONOFF MINI ONE PM pelo OpenEdge).
RELAY = {
    "~": "sonoff/1gsp-a1b2c3",
    "name": None,
    "uniq_id": "1gsp-a1b2c3-relay",
    "cmd_t": "~/switch/0/set",
    "stat_t": "~/status/switch:0",
    "val_tpl": "{{ 'ON' if value_json.output else 'OFF' }}",
    "avty_t": "~/online",
    "pl_avail": "true",
    "pl_not_avail": "false",
    "dev": DEVICE,
}


def sensor(cls: str, unit: str, field: str) -> dict:
    return {
        "~": "sonoff/1gsp-a1b2c3",
        "name": cls,
        "uniq_id": f"1gsp-a1b2c3-{cls}",
        "stat_t": "~/status/switch:0",
        "val_tpl": "{{ value_json." + field + " }}",
        "dev_cla": cls,
        "unit_of_meas": unit,
        "dev": DEVICE,
    }


DISCOVERY = {
    f"{PREFIX}/switch/1gsp-a1b2c3/relay/config": RELAY,
    f"{PREFIX}/sensor/1gsp-a1b2c3/power/config": sensor("power", "W", "apower"),
    f"{PREFIX}/sensor/1gsp-a1b2c3/voltage/config": sensor("voltage", "V", "voltage"),
    f"{PREFIX}/sensor/1gsp-a1b2c3/current/config": sensor("current", "A", "current"),
    f"{PREFIX}/sensor/1gsp-a1b2c3/energy/config": sensor("energy", "kWh", "aenergy"),
}
STATUS = {"output": True, "apower": 41.5, "voltage": 126.8, "current": 0.33, "aenergy": 1.2}


def entities():
    out = []
    for topic, config in DISCOVERY.items():
        out += parse_discovery(PREFIX, topic, json.dumps(config).encode())[1]
    return out


def test_template_is_sandboxed():
    assert render("{{ value_json.a.b }}", '{"a": {"b": 3}}') == "3"
    assert render("{{ value_json.missing }}", "{}") is None
    assert render("{{ value_json.x | is_defined }}", "{}") is None
    assert render(None, "ON") == "ON"
    assert render("{{ ''.__class__.__mro__ }}", "x") is None
    assert (
        render(
            "{% for i in range(99999) %}{% for j in range(99999) %}{% endfor %}{% endfor %}", "x"
        )
        is None
    )
    assert render("{{ 'a' * 10**9 }}", "x") is None
    assert render("{{ 9 ** 99999999 }}", "x") is None
    assert render("{{ 'ON' if value == '1' else 'OFF' }}", "1") == "ON"


def test_discovery_groups_relay_and_sensors():
    [candidate] = group_candidates(entities())
    assert candidate.name == "MINI-1GSP"
    assert candidate.kind == "relay"
    assert candidate.product_name == "SONOFF MINI ONE PM"
    assert candidate.capabilities == ["power", "energy"]
    # O sensor de energia acumulada fica de fora: o Cordyhome calcula o consumo pela potência.
    assert sorted(s.device_class for s in candidate.sensors) == ["current", "power", "voltage"]
    assert candidate.control.command_topic == "sonoff/1gsp-a1b2c3/switch/0/set"
    assert candidate.control.availability[0].topic == "sonoff/1gsp-a1b2c3/online"


def test_device_discovery_format_and_json_light():
    payload = {
        "dev": {"ids": "lamp1", "name": "Luminária"},
        "avty_t": "lamp1/availability",
        "cmps": {
            "light": {
                "p": "light",
                "schema": "json",
                "brightness": True,
                "cmd_t": "lamp1/set",
                "stat_t": "lamp1/state",
            },
            "button": {"p": "button", "cmd_t": "lamp1/identify"},
        },
    }
    topic = f"{PREFIX}/device/lamp1/config"
    keys, found = parse_discovery(PREFIX, topic, json.dumps(payload).encode())
    assert keys == ["lamp1/light"]
    [light] = found
    assert light.availability[0].topic == "lamp1/availability"
    [candidate] = group_candidates(found)
    assert (candidate.kind, candidate.capabilities) == ("light", ["power", "brightness"])


def test_ignores_other_topics_and_bad_payloads():
    assert parse_discovery(PREFIX, "other/switch/x/config", b"{}") == ([], [])
    assert parse_discovery(PREFIX, f"{PREFIX}/switch/x/config", b"not json") == ([], [])
    assert parse_discovery(PREFIX, f"{PREFIX}/switch/x/config", b"") == ([], [])
    # Interruptor sem tópico de comando não serve para controle.
    assert parse_discovery(PREFIX, f"{PREFIX}/switch/x/config", b'{"stat_t": "a"}') == ([], [])


class FakeConnection:
    def __init__(self):
        self.connected = True
        self.messages: dict[str, Message] = {}
        self.sent: list[tuple[str, str]] = []

    async def publish(self, topic, payload, qos=0):
        self.sent.append((topic, payload))

    def put(self, topic, payload, ts=1.0):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.messages[topic] = Message(text, ts)


def ref_for(candidate) -> DeviceRef:
    config = {
        "control": candidate.control.to_dict() if candidate.control else None,
        "sensors": [s.to_dict() for s in candidate.sensors],
        "capabilities": candidate.capabilities,
    }
    return DeviceRef(id=1, external_id=candidate.key, config=json.loads(json.dumps(config)))


def test_adapter_reads_cached_state_and_sends_commands():
    [candidate] = group_candidates(entities())
    device = ref_for(candidate)
    conn = FakeConnection()
    adapter = MqttAdapter(conn)

    with pytest.raises(AdapterError, match="sem notícias"):
        asyncio.run(adapter.read(device))

    conn.put("sonoff/1gsp-a1b2c3/online", "true")
    conn.put("sonoff/1gsp-a1b2c3/status/switch:0", STATUS)
    reading = asyncio.run(adapter.read(device))
    assert (reading.is_on, reading.power_w, reading.voltage_v, reading.current_a) == (
        True,
        41.5,
        126.8,
        0.33,
    )

    asyncio.run(adapter.set_power(device, False))
    assert conn.sent == [("sonoff/1gsp-a1b2c3/switch/0/set", "OFF")]

    conn.put("sonoff/1gsp-a1b2c3/online", "false", ts=2.0)
    with pytest.raises(AdapterError, match="desconectado"):
        asyncio.run(adapter.read(device))

    conn.connected = False
    with pytest.raises(AdapterError, match="servidor MQTT"):
        asyncio.run(adapter.set_power(device, True))


def test_adapter_json_light_brightness():
    payload = {
        "dev": {"ids": "l2", "name": "Abajur"},
        "schema": "json",
        "brightness": True,
        "bri_scl": 254,
        "cmd_t": "z2m/abajur/set",
        "stat_t": "z2m/abajur",
    }
    _, found = parse_discovery(PREFIX, f"{PREFIX}/light/l2/config", json.dumps(payload).encode())
    [candidate] = group_candidates(found)
    device = ref_for(candidate)
    conn = FakeConnection()
    adapter = MqttAdapter(conn)
    conn.put("z2m/abajur", {"state": "ON", "brightness": 127})
    reading = asyncio.run(adapter.read(device))
    assert reading.is_on is True and reading.state == {"brightness": 50}
    asyncio.run(adapter.set_state(device, {"brightness": 100}))
    assert json.loads(conn.sent[-1][1]) == {"state": "ON", "brightness": 254}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def wait_for(condition, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("tempo esgotado")


def test_embedded_broker_end_to_end(svc):
    """Servidor embutido + aparelho de mentira: descoberta, importação, leitura e comando."""
    port = free_port()

    async def scenario():
        status = await svc.mqtt.configure({"enabled": True, "mode": "embedded", "port": port})
        password = status["password"]
        assert status["username"] == "cordyhome" and len(password) == 16
        await wait_for(lambda: svc.mqtt.connected)

        # Sem a senha, o servidor recusa.
        intruder = MQTTClient(config={"auto_reconnect": False})
        with pytest.raises(ConnectError):
            await intruder.connect(f"mqtt://cordyhome:errada@127.0.0.1:{port}")

        device = MQTTClient(config={"auto_reconnect": False})
        await device.connect(f"mqtt://cordyhome:{password}@127.0.0.1:{port}")
        await device.subscribe([("sonoff/1gsp-a1b2c3/switch/0/set", 0)])
        for topic, config in DISCOVERY.items():
            await device.publish(topic, json.dumps(config).encode(), retain=True)
        await device.publish("sonoff/1gsp-a1b2c3/online", b"true", retain=True)
        await device.publish("sonoff/1gsp-a1b2c3/status/switch:0", json.dumps(STATUS).encode())
        await wait_for(lambda: len(svc.mqtt.candidates()) == 1)

        [candidate] = svc.mqtt.candidates()
        assert candidate["capabilities"] == ["power", "energy"]
        [device_id] = svc.mqtt.import_devices([{"id": candidate["id"], "name": "Bomba d'água"}])
        await svc.hub.refresh(device_id)
        info = svc.hub.device(device_id)
        assert (info["online"], info["is_on"], info["power_w"]) == (True, True, 41.5)
        assert info["info"]["has_energy_meter"] is True

        await svc.hub.set_power(device_id, False)
        message = await device.deliver_message(timeout_duration=5)
        assert bytes(message.data) == b"OFF"

        # O aparelho confirma pelo tópico de estado e a tela é atualizada sozinha.
        off = {**STATUS, "output": False, "apower": 0}
        await device.publish("sonoff/1gsp-a1b2c3/status/switch:0", json.dumps(off).encode())
        await wait_for(lambda: svc.hub.device(device_id)["power_w"] == 0)

        await device.disconnect()
        await svc.mqtt.disable()
        assert svc.mqtt.status()["enabled"] is False and not svc.mqtt.connected
        await svc.hub.stop()

    asyncio.run(scenario())


def test_mqtt_api(authed):
    assert authed.get("/api/mqtt").json()["enabled"] is False
    r = authed.put("/api/mqtt", json={"enabled": True, "mode": "external", "host": " "})
    assert r.status_code == 422
    assert authed.get("/api/mqtt/devices").json() == []
    assert authed.post("/api/mqtt/import", json={"devices": [{"id": "x"}]}).json() == {
        "imported": []
    }


def test_external_broker_wrong_password_is_reported(svc):
    port = free_port()

    async def scenario():
        await svc.mqtt.configure({"enabled": True, "port": port})
        await wait_for(lambda: svc.mqtt.connected)
        broker = svc.mqtt._broker
        svc.mqtt._broker = None  # mantém o servidor no ar ao trocar para "externo"
        await svc.mqtt.configure(
            {"mode": "external", "host": "127.0.0.1", "username": "cordyhome", "password": "x"}
        )
        await wait_for(lambda: svc.mqtt.error is not None)
        assert "usuário ou a senha" in svc.mqtt.error
        assert svc.mqtt.status()["password"] is None
        await svc.mqtt.disable()
        await broker.stop()

    asyncio.run(scenario())
