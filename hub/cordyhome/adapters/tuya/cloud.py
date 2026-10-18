"""Vínculo com a conta do app Tuya Smart / Smart Life, usado só para obter as chaves locais.

Usa o SDK oficial de compartilhamento de dispositivos da Tuya (o mesmo da integração do Home
Assistant): o usuário informa o "código de usuário" do app e escaneia um QR code. Não exige
conta de desenvolvedor nem plano pago. Depois da importação, o controle é 100% local.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import segno
from tuya_sharing import LoginControl, Manager, SharingTokenListener

from ..base import AdapterError

# Credenciais públicas do cliente de compartilhamento da Tuya. A Tuya só emite esse tipo de
# credencial para parceiros, por isso o app de celular mostrará "Home Assistant" ao autorizar.
CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
SCHEMA = "haauthorize"

LOGIN_TTL = 5 * 60

CATEGORY_KIND = {
    "cz": "plug",  # tomada
    "pc": "plug",  # filtro de linha
    "kg": "switch",  # interruptor
    "tdq": "switch",  # disjuntor
    "dj": "light",
    "dd": "light",
    "xdd": "light",
    "fwd": "light",
}


@dataclass
class PendingLogin:
    user_code: str
    token: str
    created: float = field(default_factory=time.time)


@dataclass
class CloudDevice:
    id: str
    name: str
    category: str
    product_name: str
    local_key: str
    online: bool
    support_local: bool
    local_strategy: dict[int, dict[str, Any]]
    room: str | None

    @property
    def kind(self) -> str:
        return CATEGORY_KIND.get(self.category, "other")


class _TokenCapture(SharingTokenListener):
    def __init__(self) -> None:
        self.updated: dict[str, Any] | None = None

    def update_token(self, token_info: dict[str, Any]) -> None:
        self.updated = token_info


class TuyaCloud:
    def __init__(self) -> None:
        self._pending: dict[str, PendingLogin] = {}

    async def start_login(self, user_code: str) -> tuple[str, str]:
        """Retorna (token, svg do QR code) para o usuário escanear no app."""
        user_code = user_code.strip()
        response = await asyncio.to_thread(LoginControl().qr_code, CLIENT_ID, SCHEMA, user_code)
        if not response.get("success"):
            raise AdapterError(
                response.get("msg") or "Código de usuário inválido. Confira no app Tuya Smart."
            )
        token = response["result"]["qrcode"]
        self._pending[token] = PendingLogin(user_code=user_code, token=token)
        qr = segno.make(f"tuyaSmart--qrLogin?token={token}", error="m")
        # Sem tamanho fixo (só viewBox): a interface escala o QR para caber no quadro inteiro.
        # Com largura fixa, tokens maiores geravam um QR maior que o quadro e ele saía cortado.
        svg = qr.svg_inline(border=2, dark="#111", light="#fff", omitsize=True)
        return token, svg

    async def poll_login(self, token: str) -> dict[str, Any] | None:
        """Retorna os dados do vínculo quando o QR code for confirmado; None enquanto pendente."""
        pending = self._pending.get(token)
        if pending is None or time.time() - pending.created > LOGIN_TTL:
            self._pending.pop(token, None)
            raise AdapterError("O QR code expirou. Gere um novo.")
        ok, info = await asyncio.to_thread(
            LoginControl().login_result, token, CLIENT_ID, pending.user_code
        )
        if not ok:
            return None
        self._pending.pop(token, None)
        return {
            "user_code": pending.user_code,
            "terminal_id": info["terminal_id"],
            "endpoint": info["endpoint"],
            "username": info.get("username"),
            "token": {
                "t": info["t"],
                "uid": info["uid"],
                "expire_time": info["expire_time"],
                "access_token": info["access_token"],
                "refresh_token": info["refresh_token"],
            },
        }

    async def fetch_devices(self, link: dict[str, Any]) -> tuple[list[CloudDevice], dict | None]:
        """Lista os dispositivos da conta. Retorna também o token renovado, se houver."""

        def run() -> tuple[list[CloudDevice], dict | None]:
            capture = _TokenCapture()
            manager = Manager(
                CLIENT_ID,
                link["user_code"],
                link["terminal_id"],
                link["endpoint"],
                link["token"],
                capture,
            )
            manager.update_device_cache()
            devices: list[CloudDevice] = []
            for dev in manager.device_map.values():
                room = manager.query_room_by_device(dev.id)
                devices.append(
                    CloudDevice(
                        id=dev.id,
                        name=dev.name,
                        category=getattr(dev, "category", "") or "",
                        product_name=getattr(dev, "product_name", "") or "",
                        local_key=getattr(dev, "local_key", "") or "",
                        online=bool(getattr(dev, "online", False)),
                        support_local=bool(getattr(dev, "support_local", False)),
                        local_strategy=getattr(dev, "local_strategy", {}) or {},
                        room=room.name if room else None,
                    )
                )
            return devices, capture.updated

        try:
            return await asyncio.to_thread(run)
        except KeyError as exc:
            raise AdapterError(
                "A sessão com a conta Tuya expirou. Vincule a conta de novo."
            ) from exc
        except Exception as exc:  # noqa: BLE001 - erros de rede/SDK
            raise AdapterError(f"Não foi possível falar com a nuvem Tuya: {exc}") from exc
