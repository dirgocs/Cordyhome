"""Dados de demonstração: casa com tomadas simuladas e 60 dias de histórico de consumo."""

from __future__ import annotations

import json
import math
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..db import Database

ROOMS = ["Sala", "Cozinha", "Quarto", "Escritório", "Área de serviço"]

# nome, cômodo, tipo, watts ligado, perfil de uso (horas do dia em que costuma estar ligado)
DEVICES = [
    ("TV", "Sala", "plug", 95, range(19, 24)),
    ("Luminária de chão", "Sala", "light", 12, range(18, 24)),
    ("Geladeira", "Cozinha", "plug", 140, range(0, 24)),
    ("Cafeteira", "Cozinha", "plug", 800, [7]),
    ("Micro-ondas", "Cozinha", "plug", 1100, [12, 20]),
    ("Ar-condicionado", "Quarto", "plug", 850, [0, 1, 2, 3, 4, 5, 22, 23]),
    ("Carregador do celular", "Quarto", "plug", 8, [0, 1, 2, 3, 4, 5]),
    ("Computador", "Escritório", "plug", 180, range(9, 18)),
    ("Monitor", "Escritório", "plug", 28, range(9, 18)),
    ("Máquina de lavar", "Área de serviço", "plug", 450, [10]),
]


def seed_demo(db: Database, tz: str = "America/Sao_Paulo", days: int = 60) -> None:
    if db.scalar("SELECT COUNT(*) FROM devices"):
        return
    now = int(time.time())
    rng = random.Random(42)
    zone = ZoneInfo(tz)
    with db.transaction():
        room_ids = {}
        for order, name in enumerate(ROOMS):
            cur = db.execute(
                "INSERT INTO rooms (name, sort_order, created_at) VALUES (?,?,?)",
                (name, order, now),
            )
            room_ids[name] = cur.lastrowid

        start_hour = (now - days * 86400) // 3600 * 3600
        for index, (name, room, kind, watts, hours) in enumerate(DEVICES):
            hour_now = datetime.fromtimestamp(now, zone).hour
            config = {
                "watts": watts,
                "standby_watts": 0.5 if watts > 50 else 0.2,
                "initially_on": hour_now in hours or name == "Geladeira",
            }
            cur = db.execute(
                "INSERT INTO devices (name, room_id, kind, adapter, external_id, config, "
                "sort_order, created_at, power_alert_watts) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    name,
                    room_ids[room],
                    kind,
                    "simulator",
                    f"sim-{index}",
                    json.dumps(config),
                    index,
                    now,
                    1500 if watts > 500 else None,
                ),
            )
            device_id = cur.lastrowid
            rows = []
            for ts in range(start_hour, now - 3600, 3600):
                local = datetime.fromtimestamp(ts, zone)
                on = local.hour in hours and rng.random() > 0.15
                if name == "Geladeira":
                    duty = 0.45 + 0.1 * math.sin(local.hour / 24 * math.tau)
                    wh = watts * duty
                elif on:
                    wh = watts * rng.uniform(0.35, 1.0)
                else:
                    wh = config["standby_watts"]
                rows.append((device_id, ts, round(wh, 3)))
            db.executemany("INSERT INTO energy_hour (device_id, ts, wh) VALUES (?,?,?)", rows)

        schedules = [
            ("Cafeteira", "on", "06:50", 0b0111110),
            ("Cafeteira", "off", "07:30", 0b0111110),
            ("Ar-condicionado", "off", "06:00", 0b1111111),
        ]
        for device_name, action, at, days_mask in schedules:
            device_id = db.scalar("SELECT id FROM devices WHERE name = ?", (device_name,))
            db.execute(
                "INSERT INTO schedules (device_id, action, time, days, created_at) "
                "VALUES (?,?,?,?,?)",
                (device_id, action, at, days_mask, now),
            )
