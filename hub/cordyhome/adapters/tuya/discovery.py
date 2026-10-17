"""Descoberta de dispositivos Tuya na rede local.

As tomadas Tuya anunciam-se por broadcast UDP (portas 6666/6667/7000) com id, IP e versão
do protocolo. É assim que descobrimos o IP local, que a nuvem não informa.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from tinytuya import scanner

log = logging.getLogger(__name__)


@dataclass
class LanDevice:
    id: str
    ip: str
    version: float | None


def _scan(scantime: int, want_ids: list[str] | None) -> list[LanDevice]:
    found = scanner.devices(
        verbose=False,
        scantime=scantime,
        color=False,
        poll=False,
        byID=True,
        show_timer=False,
        wantids=want_ids or None,
        maxdevices=len(want_ids) if want_ids else 0,
        tuyadevices=[],
        assume_yes=True,
    )
    result: list[LanDevice] = []
    for dev_id, info in (found or {}).items():
        ip = info.get("ip")
        if not ip:
            continue
        try:
            version = float(info.get("version")) if info.get("version") else None
        except (TypeError, ValueError):
            version = None
        result.append(LanDevice(id=str(dev_id), ip=str(ip), version=version))
    return result


async def scan_lan(scantime: int = 10, want_ids: list[str] | None = None) -> list[LanDevice]:
    try:
        return await asyncio.to_thread(_scan, scantime, want_ids)
    except OSError as exc:
        # Porta UDP ocupada (outro app Tuya rodando) ou rede sem broadcast.
        log.warning("Busca Tuya na rede falhou: %s", exc)
        return []
