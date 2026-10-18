"""Fluxo de configuração das tomadas Tuya: vincular conta → listar → importar → controle local."""

from __future__ import annotations

import json
import time
from typing import Any

from ..adapters.tuya.cloud import CloudDevice, TuyaCloud
from ..adapters.tuya.discovery import LanDevice, scan_lan
from ..adapters.tuya.dps import DpMap, default_dp_map, dp_map_from_strategy
from ..db import Database
from ..settings import SettingsStore
from .hub import Hub

LINK_KEY = "tuya.link"


class TuyaLinkService:
    def __init__(self, db: Database, settings: SettingsStore, hub: Hub, cloud: TuyaCloud):
        self.db = db
        self.settings = settings
        self.hub = hub
        self.cloud = cloud
        self._candidates: dict[str, CloudDevice] = {}
        self._lan: dict[str, LanDevice] = {}

    # ------------------------------------------------------------------ vínculo

    def status(self) -> dict[str, Any]:
        link = self.settings.get_json(LINK_KEY)
        imported = self.db.scalar("SELECT COUNT(*) FROM devices WHERE adapter = 'tuya'")
        return {
            "linked": link is not None,
            "username": link.get("username") if link else None,
            "linked_at": link.get("linked_at") if link else None,
            "imported_devices": imported,
        }

    async def start_login(self, user_code: str) -> dict[str, str]:
        token, svg = await self.cloud.start_login(user_code)
        return {"token": token, "qr_svg": svg}

    async def poll_login(self, token: str) -> bool:
        link = await self.cloud.poll_login(token)
        if link is None:
            return False
        link["linked_at"] = int(time.time())
        self.settings.set_json(LINK_KEY, link)
        return True

    def unlink(self) -> None:
        self.settings.set_json(LINK_KEY, None)
        self._candidates.clear()

    # ------------------------------------------------------------------ descoberta

    async def candidates(self) -> list[dict[str, Any]]:
        link = self.settings.get_json(LINK_KEY)
        if link is None:
            return []
        devices, refreshed = await self.cloud.fetch_devices(link)
        if refreshed:
            link["token"] = refreshed
            self.settings.set_json(LINK_KEY, link)
        self._candidates = {d.id: d for d in devices}
        keys = {d.id: d.local_key for d in devices if d.local_key}
        await self._scan(list(self._candidates), keys)

        existing = {
            row["external_id"]: row["id"]
            for row in self.db.all("SELECT id, external_id FROM devices WHERE adapter = 'tuya'")
        }
        out = []
        for dev in devices:
            mapping = dp_map_from_strategy(dev.local_strategy)
            lan_dev = self._lan.get(dev.id)
            out.append(
                {
                    "id": dev.id,
                    "name": dev.name,
                    "room": dev.room,
                    "kind": dev.kind,
                    "product_name": dev.product_name,
                    "cloud_online": dev.online,
                    "local_supported": bool(dev.local_key),
                    "has_energy_meter": bool(mapping and mapping.power),
                    "lan_ip": lan_dev.ip if lan_dev else None,
                    "imported_device_id": existing.get(dev.id),
                }
            )
        return sorted(out, key=lambda d: (d["room"] or "~", d["name"].lower()))

    async def rescan(self) -> int:
        """Atualiza IPs e versões das tomadas já importadas. Retorna quantas mudaram."""
        rows = self.db.all(
            "SELECT id, external_id, config, adapter FROM devices WHERE adapter='tuya'"
        )
        if not rows:
            return 0
        keys = {
            r["external_id"]: key for r in rows if (key := json.loads(r["config"]).get("local_key"))
        }
        await self._scan([r["external_id"] for r in rows], keys)
        changed = 0
        for row in rows:
            found = self._lan.get(row["external_id"])
            cfg = json.loads(row["config"])
            if not found:
                continue
            new_version = found.version or cfg.get("version")
            if cfg.get("ip") != found.ip or cfg.get("version") != new_version:
                cfg.update(ip=found.ip, version=new_version, version_confirmed=bool(found.version))
                self.db.execute(
                    "UPDATE devices SET config = ? WHERE id = ?", (json.dumps(cfg), row["id"])
                )
                self.hub.forget(row["id"], row["adapter"])
                changed += 1
        return changed

    async def _scan(self, want_ids: list[str], keys: dict[str, str]) -> list[LanDevice]:
        """Broadcast na rede do hub e, se configuradas, varredura das faixas das tomadas."""
        networks = self.settings.get().lan_networks
        lan = await scan_lan(scantime=8, want_ids=want_ids, networks=networks, keys=keys)
        self._lan.update({d.id: d for d in lan})
        return lan

    # ------------------------------------------------------------------ importação

    def import_devices(self, selections: list[dict[str, Any]]) -> list[int]:
        """Cria (ou atualiza chaves/IPs de) dispositivos escolhidos na lista de candidatos."""
        now = int(time.time())
        rooms = {
            row["name"].strip().lower(): row["id"]
            for row in self.db.all("SELECT id, name FROM rooms")
        }
        imported: list[int] = []
        with self.db.transaction():
            for selection in selections:
                dev = self._candidates.get(selection["id"])
                if dev is None or not dev.local_key:
                    continue
                room_id = self._room_id(selection.get("room", dev.room), rooms, now)
                lan_dev = self._lan.get(dev.id)
                mapping: DpMap = dp_map_from_strategy(dev.local_strategy) or default_dp_map()
                config = {
                    "local_key": dev.local_key,
                    "ip": lan_dev.ip if lan_dev else None,
                    "version": (lan_dev.version if lan_dev and lan_dev.version else 3.3),
                    "version_confirmed": bool(lan_dev and lan_dev.version),
                    "dp_map": mapping.to_dict(),
                    "product_name": dev.product_name,
                    "category": dev.category,
                }
                existing = self.db.one(
                    "SELECT id, config FROM devices WHERE adapter = 'tuya' AND external_id = ?",
                    (dev.id,),
                )
                if existing:
                    old = json.loads(existing["config"])
                    config["ip"] = config["ip"] or old.get("ip")
                    self.db.execute(
                        "UPDATE devices SET config = ? WHERE id = ?",
                        (json.dumps(config), existing["id"]),
                    )
                    self.hub.forget(existing["id"], "tuya")
                    imported.append(existing["id"])
                    continue
                cur = self.db.execute(
                    "INSERT INTO devices (name, room_id, kind, adapter, external_id, config, "
                    "created_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        (selection.get("name") or dev.name).strip(),
                        room_id,
                        dev.kind,
                        "tuya",
                        dev.id,
                        json.dumps(config),
                        now,
                    ),
                )
                imported.append(int(cur.lastrowid))
        self.hub.bus.publish("devices")
        return imported

    def _room_id(self, name: str | None, rooms: dict[str, int], now: int) -> int | None:
        if not name or not name.strip():
            return None
        key = name.strip().lower()
        if key not in rooms:
            order = self.db.scalar("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM rooms")
            cur = self.db.execute(
                "INSERT INTO rooms (name, sort_order, created_at) VALUES (?,?,?)",
                (name.strip(), order, now),
            )
            rooms[key] = int(cur.lastrowid)
        return rooms[key]
