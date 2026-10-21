"""Integração MQTT: servidor embutido (ou externo), descoberta e importação de aparelhos.

Os aparelhos SONOFF OpenEdge, Tasmota, ESPHome e afins se conectam ao servidor MQTT,
anunciam as entidades no formato do Home Assistant e publicam o estado sozinhos. O serviço
guarda a última mensagem de cada tópico; o adaptador `mqtt` lê dela e publica os comandos.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import socket
import string
import time
from typing import Any, Literal
from urllib.parse import quote

from amqtt.client import MQTTClient
from amqtt.mqtt.constants import QOS_0
from pydantic import BaseModel, Field

from ..adapters.mqtt.adapter import Message, device_entities
from ..adapters.mqtt.broker import EmbeddedBroker
from ..adapters.mqtt.discovery import Candidate, Entity, group_candidates, parse_discovery
from ..db import Database
from ..settings import SettingsStore
from .hub import Hub

log = logging.getLogger(__name__)
# O amqtt registra cada tentativa de reconexão como aviso; o estado já aparece na tela.
logging.getLogger("amqtt").setLevel(logging.ERROR)

CONFIG_KEY = "mqtt.config"
MAX_TOPICS = 5000
MAX_PAYLOAD = 64 * 1024
PUSH_INTERVAL = 1.0  # no máximo uma atualização imediata por aparelho por segundo
RETRY_MAX = 30.0


class MqttSettings(BaseModel):
    enabled: bool = False
    # embedded: o Cordyhome é o servidor; external: usa um servidor que já existe na casa.
    mode: Literal["embedded", "external"] = "embedded"
    host: str = Field("", max_length=253)
    port: int = Field(1883, ge=1, le=65535)
    username: str = Field("", max_length=64)
    password: str = Field("", max_length=128)
    discovery_prefix: str = Field("homeassistant", min_length=1, max_length=64)


def _new_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def local_addresses() -> list[str]:
    """IPs locais deste computador, para o usuário digitar no aparelho."""
    found: list[str] = []
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        # Não envia nada: só descobre por qual interface sai a rota padrão.
        s.connect(("192.0.2.1", 9))
        found.append(s.getsockname()[0])
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(str(info[4][0]))
    out: list[str] = []
    for ip in found:
        if not ip.startswith("127.") and ip not in out:
            out.append(ip)
    return out


class MqttLinkService:
    def __init__(self, db: Database, settings: SettingsStore, hub: Hub):
        self.db = db
        self.settings = settings
        self.hub = hub
        self.connected = False
        self.error: str | None = None
        self.messages: dict[str, Message] = {}
        self.entities: dict[str, Entity] = {}
        self._discovery: dict[str, list[str]] = {}  # tópico de descoberta → entidades
        self._watch: dict[str, set[int]] = {}  # tópico de estado → aparelhos importados
        self._last_push: dict[int, float] = {}
        self._broker: EmbeddedBroker | None = None
        self._client: MQTTClient | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ configuração

    def config(self) -> MqttSettings:
        return MqttSettings(**(self.settings.get_json(CONFIG_KEY) or {}))

    def _save(self, config: MqttSettings) -> None:
        self.settings.set_json(CONFIG_KEY, config.model_dump())

    async def configure(self, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.config()
        config = MqttSettings(**{**current.model_dump(), **changes})
        if config.mode == "embedded":
            if current.mode != "embedded" or not config.password:
                config.username, config.password = "cordyhome", _new_password()
            config.host = ""
        elif not config.host.strip():
            raise ValueError("Informe o endereço do servidor MQTT.")
        self._save(config)
        await self.restart()
        return self.status()

    async def new_password(self) -> dict[str, Any]:
        config = self.config()
        if config.mode != "embedded":
            raise ValueError("A senha só pode ser gerada para o servidor do Cordyhome.")
        config.password = _new_password()
        self._save(config)
        await self.restart()
        return self.status()

    def status(self) -> dict[str, Any]:
        config = self.config()
        imported = self.db.scalar("SELECT COUNT(*) FROM devices WHERE adapter = 'mqtt'")
        embedded = config.mode == "embedded"
        return {
            "linked": config.enabled,
            "enabled": config.enabled,
            "mode": config.mode,
            "connected": self.connected,
            "error": self.error,
            "host": config.host,
            "port": config.port,
            "username": config.username,
            # Só a senha do servidor embutido aparece: é o usuário que vai digitá-la no aparelho.
            "password": config.password if embedded else None,
            "addresses": local_addresses() if embedded else [],
            "discovery_prefix": config.discovery_prefix,
            "discovered_devices": len(group_candidates(list(self.entities.values()))),
            "imported_devices": imported,
        }

    # ------------------------------------------------------------------ ciclo de vida

    async def start(self) -> None:
        async with self._lock:
            await self._start()

    async def stop(self) -> None:
        async with self._lock:
            await self._stop()

    async def restart(self) -> None:
        async with self._lock:
            await self._stop()
            await self._start()

    async def _start(self) -> None:
        config = self.config()
        if not config.enabled:
            return
        self._rebuild_watch()
        if config.mode == "embedded":
            broker = EmbeddedBroker("0.0.0.0", config.port, config.username, config.password)
            try:
                await broker.start()
            except Exception as exc:  # noqa: BLE001
                log.warning("Servidor MQTT não iniciou: %s", exc)
                self.error = (
                    f"Não consegui abrir a porta {config.port}. Outro programa pode estar "
                    "usando essa porta."
                )
                return
            self._broker = broker
        self._task = asyncio.create_task(self._run(config), name="mqtt")

    async def _stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._broker is not None:
            await self._broker.stop()
            self._broker = None
        self.connected = False
        self.error = None
        self.messages.clear()
        self.entities.clear()
        self._discovery.clear()

    def _uri(self, config: MqttSettings) -> str:
        host = "127.0.0.1" if config.mode == "embedded" else config.host.strip()
        auth = ""
        if config.username:
            auth = quote(config.username, safe="")
            if config.password:
                auth += ":" + quote(config.password, safe="")
            auth += "@"
        return f"mqtt://{auth}{host}:{config.port}"

    async def _run(self, config: MqttSettings) -> None:
        """Mantém o cliente conectado, reconectando com espera crescente."""
        delay = 1.0
        prefix = config.discovery_prefix.strip("/")
        while True:
            client = MQTTClient(
                client_id=f"cordyhome-{secrets.token_hex(4)}",
                config={"auto_reconnect": False, "keep_alive": 30},
            )
            try:
                await client.connect(self._uri(config))
                self._client = client
                await client.subscribe([("#", QOS_0)])
                self.connected, self.error, delay = True, None, 1.0
                # Aviso de "Home Assistant online": os aparelhos reenviam descoberta e estado.
                await client.publish(f"{prefix}/status", b"online", qos=QOS_0)
                while True:
                    message = await client.deliver_message()
                    if message is not None:
                        self.on_message(message.topic, bytes(message.data or b""))
            except asyncio.CancelledError:
                task = asyncio.current_task()
                if task is not None and task.cancelling():
                    raise
                # O cliente cancela a espera por mensagens quando a conexão cai.
                self.error = "A conexão com o servidor MQTT caiu."
            except Exception as exc:  # noqa: BLE001
                lost = self.connected
                self.error = "A conexão com o servidor MQTT caiu." if lost else _friendly_error(exc)
                log.info("MQTT: %s (%s)", self.error, exc)
            finally:
                self.connected = False
                self._client = None
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), 2)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX)

    async def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        client = self._client
        if client is None:
            raise ConnectionError("cliente MQTT desconectado")
        await client.publish(topic, payload.encode(), qos=qos)

    # ------------------------------------------------------------------ mensagens

    def on_message(self, topic: str, payload: bytes, now: float | None = None) -> None:
        if len(payload) > MAX_PAYLOAD:
            return
        text = payload.decode("utf-8", errors="replace")
        prefix = self.config().discovery_prefix.strip("/")
        if topic.startswith(prefix + "/") and topic.endswith("/config"):
            self._on_discovery(prefix, topic, payload)
            return
        if topic not in self.messages and len(self.messages) >= MAX_TOPICS:
            return
        self.messages[topic] = Message(text, time.time() if now is None else now)
        for device_id in self._watch.get(topic, ()):
            self._push(device_id)

    def _on_discovery(self, prefix: str, topic: str, payload: bytes) -> None:
        for key in self._discovery.pop(topic, []):
            self.entities.pop(key, None)
        keys, entities = parse_discovery(prefix, topic, payload)
        if keys:
            self._discovery[topic] = keys
        for entity in entities:
            self.entities[entity.key] = entity

    def _push(self, device_id: int) -> None:
        """Mensagem nova de um aparelho importado: atualiza a tela na hora."""
        now = time.monotonic()
        if now - self._last_push.get(device_id, 0) < PUSH_INTERVAL:
            return
        self._last_push[device_id] = now
        self.hub.refresh_soon(device_id)

    def _rebuild_watch(self) -> None:
        watch: dict[str, set[int]] = {}
        for row in self.db.all("SELECT id, config FROM devices WHERE adapter = 'mqtt'"):
            control, _ = device_entities(json.loads(row["config"]))
            for topic in control.topics if control else ():
                watch.setdefault(topic, set()).add(row["id"])
        self._watch = watch

    # ------------------------------------------------------------------ descoberta

    def _candidates(self) -> dict[str, Candidate]:
        return {c.key: c for c in group_candidates(list(self.entities.values()))}

    def candidates(self) -> list[dict[str, Any]]:
        existing = {
            row["external_id"]: row["id"]
            for row in self.db.all("SELECT id, external_id FROM devices WHERE adapter = 'mqtt'")
        }
        return [
            {
                "id": c.key,
                "name": c.name,
                "kind": c.kind,
                "product_name": c.product_name,
                "capabilities": c.capabilities,
                "has_energy_meter": "energy" in c.capabilities,
                "imported_device_id": existing.get(c.key),
            }
            for c in self._candidates().values()
        ]

    def import_devices(self, selections: list[dict[str, Any]]) -> list[int]:
        candidates = self._candidates()
        now = int(time.time())
        imported: list[int] = []
        with self.db.transaction():
            for selection in selections:
                candidate = candidates.get(selection["id"])
                if candidate is None:
                    continue
                config = {
                    "control": candidate.control.to_dict() if candidate.control else None,
                    "sensors": [s.to_dict() for s in candidate.sensors],
                    "capabilities": candidate.capabilities,
                    "product_name": candidate.product_name,
                }
                existing = self.db.one(
                    "SELECT id FROM devices WHERE adapter = 'mqtt' AND external_id = ?",
                    (candidate.key,),
                )
                if existing:
                    self.db.execute(
                        "UPDATE devices SET config = ? WHERE id = ?",
                        (json.dumps(config), existing["id"]),
                    )
                    self.hub.forget(existing["id"], "mqtt")
                    imported.append(existing["id"])
                    continue
                cur = self.db.execute(
                    "INSERT INTO devices (name, room_id, kind, adapter, external_id, config, "
                    "created_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        (selection.get("name") or candidate.name).strip(),
                        selection.get("room_id"),
                        candidate.kind,
                        "mqtt",
                        candidate.key,
                        json.dumps(config),
                        now,
                    ),
                )
                imported.append(int(cur.lastrowid))
        self._rebuild_watch()
        self.hub.bus.publish("devices")
        for device_id in imported:
            self.hub.refresh_soon(device_id, delay=0)
        return imported

    async def disable(self) -> None:
        config = self.config()
        config.enabled = False
        self._save(config)
        await self.restart()


def _friendly_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()
    if "refused" in lowered or "errno 111" in lowered or "10061" in lowered:
        return "O servidor MQTT recusou a conexão. Confira o endereço e a porta."
    if "rejected" in lowered or "not authori" in lowered:
        return "O servidor MQTT recusou o usuário ou a senha."
    if "getaddrinfo" in lowered or "name or service" in lowered:
        return "Não encontrei o servidor MQTT nesse endereço."
    return f"Falha na conexão MQTT: {text}"
