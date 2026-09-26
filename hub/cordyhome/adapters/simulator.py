"""Tomadas simuladas, para desenvolvimento e demonstração sem hardware."""

from __future__ import annotations

import math
import random
import time

from .base import DeviceReading, DeviceRef


class SimulatorAdapter:
    name = "simulator"

    def __init__(self) -> None:
        self._on: dict[int, bool] = {}

    async def read(self, device: DeviceRef) -> DeviceReading:
        cfg = device.config
        if cfg.get("flaky") and random.random() < 0.15:
            return DeviceReading(online=False)
        on = self._on.setdefault(device.id, bool(cfg.get("initially_on", True)))
        base = float(cfg.get("watts", device.nominal_watts or 60))
        standby = float(cfg.get("standby_watts", 0.4))
        if on:
            # Variação suave + ruído, para os gráficos parecerem com consumo real.
            wave = 1 + 0.12 * math.sin(time.time() / 90 + device.id)
            power = max(0.0, base * wave + random.uniform(-0.03, 0.03) * base)
        else:
            power = standby
        voltage = 127 + random.uniform(-2, 2)
        return DeviceReading(
            online=True,
            is_on=on,
            power_w=round(power, 1),
            voltage_v=round(voltage, 1),
            current_a=round(power / voltage, 3),
        )

    async def set_power(self, device: DeviceRef, on: bool) -> DeviceReading | None:
        self._on[device.id] = on
        return await self.read(device)

    def forget(self, device_id: int) -> None:
        self._on.pop(device_id, None)
