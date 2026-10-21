"""Servidor MQTT embutido, para quem não tem um na rede.

Aceita conexões só com o usuário e a senha que o Cordyhome gerou e mostra na tela.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass

from amqtt.broker import Broker
from amqtt.plugins.base import BaseAuthPlugin
from amqtt.session import Session

log = logging.getLogger(__name__)


class PasswordAuth(BaseAuthPlugin):
    """Libera quem informar o usuário e a senha configurados."""

    @dataclass
    class Config:
        username: str = ""
        password: str = ""

    async def authenticate(self, *, session: Session) -> bool:
        username, password = self.config.username, self.config.password
        if not username or not password:
            return False
        return hmac.compare_digest(session.username or "", username) and hmac.compare_digest(
            session.password or "", password
        )


class EmbeddedBroker:
    def __init__(self, host: str, port: int, username: str, password: str):
        self._config = {
            "listeners": {"default": {"type": "tcp", "bind": f"{host}:{port}"}},
            "plugins": {
                f"{PasswordAuth.__module__}.PasswordAuth": {
                    "username": username,
                    "password": password,
                },
            },
        }
        self._broker: Broker | None = None

    async def start(self) -> None:
        broker = Broker(self._config)
        await broker.start()
        self._broker = broker

    async def stop(self) -> None:
        if self._broker is not None:
            broker, self._broker = self._broker, None
            try:
                await broker.shutdown()
            except Exception:  # noqa: BLE001 - desligar nunca pode travar o hub
                log.exception("Falha ao desligar o servidor MQTT")
