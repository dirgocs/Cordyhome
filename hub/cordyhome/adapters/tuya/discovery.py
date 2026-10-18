"""Descoberta de dispositivos Tuya na rede local.

As tomadas Tuya anunciam-se por broadcast UDP (portas 6666/6667/7000) com id, IP e versão
do protocolo. É assim que descobrimos o IP local, que a nuvem não informa.

Broadcast não passa de uma rede para outra. Quando as tomadas ficam numa rede separada (uma
VLAN só para IoT, por exemplo), o hub testa a porta TCP 6668 de cada endereço das faixas
configuradas e reconhece cada tomada pela chave local que veio da conta.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from dataclasses import dataclass

from tinytuya import scanner

log = logging.getLogger(__name__)

# Uma faixa maior que /22 (1024 endereços) deixaria a busca lenta demais.
MIN_PREFIX = 22
MAX_NETWORKS = 4


@dataclass
class LanDevice:
    id: str
    ip: str
    version: float | None


def normalize_network(value: str) -> str:
    """Valida uma faixa de rede ('192.168.20.0/24' ou um IP) e devolve a forma canônica."""
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError(f"Faixa inválida: {value!r}. Use o formato 192.168.20.0/24.") from exc
    if network.version != 4 or not network.is_private:
        raise ValueError(f"{network} não é uma rede local (IPv4 privada).")
    if network.prefixlen < MIN_PREFIX:
        raise ValueError(f"{network} é grande demais; use no máximo /{MIN_PREFIX}.")
    return str(network)


def _scan(
    scantime: int,
    want_ids: list[str] | None,
    networks: list[str] | None,
    keys: dict[str, str] | None,
    discover: bool = True,
) -> list[LanDevice]:
    # A varredura por faixa precisa das chaves: é com elas que cada tomada é identificada.
    force = bool(networks and keys)
    found = scanner.devices(
        verbose=False,
        scantime=scantime,
        color=False,
        poll=False,
        byID=True,
        show_timer=False,
        discover=discover,
        forcescan=list(networks) if force else False,
        wantids=want_ids or None,
        maxdevices=len(want_ids) if want_ids else 0,
        tuyadevices=[{"id": i, "key": k, "name": ""} for i, k in keys.items()] if force else [],
        assume_yes=True,
    )
    result: list[LanDevice] = []
    for dev_id, info in (found or {}).items():
        ip = info.get("ip")
        if not dev_id or not ip:
            continue
        try:
            version = float(info.get("version")) if info.get("version") else None
        except (TypeError, ValueError):
            version = None
        result.append(LanDevice(id=str(dev_id), ip=str(ip), version=version or None))
    return result


async def scan_lan(
    scantime: int = 10,
    want_ids: list[str] | None = None,
    networks: list[str] | None = None,
    keys: dict[str, str] | None = None,
) -> list[LanDevice]:
    """Procura as tomadas por broadcast e, se houver `networks`, também por faixa de IP."""
    try:
        return await asyncio.to_thread(_scan, scantime, want_ids, networks, keys)
    except OSError as exc:
        # Porta UDP ocupada (outro app Tuya rodando) ou rede sem broadcast.
        log.warning("Busca Tuya por broadcast falhou: %s", exc)
    if not (networks and keys):
        return []
    try:
        return await asyncio.to_thread(_scan, scantime, want_ids, networks, keys, False)
    except OSError as exc:
        log.warning("Busca Tuya por faixa de IP falhou: %s", exc)
        return []
