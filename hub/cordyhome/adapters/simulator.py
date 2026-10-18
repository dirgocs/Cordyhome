"""Aparelhos simulados, para desenvolvimento e demonstração sem hardware."""

from __future__ import annotations

import math
import random
import time
from typing import Any

from .base import BRIGHTNESS, ENERGY, POWER, DeviceReading, DeviceRef


class SimulatorAdapter:
    name = "simulator"

    def __init__(self) -> None:
        self._on: dict[int, bool] = {}
        self._state: dict[int, dict[str, Any]] = {}

    def capabilities(self, config: dict[str, Any]) -> list[str]:
        return list(config.get("capabilities") or [POWER, ENERGY])

    async def read(self, device: DeviceRef) -> DeviceReading:
        cfg = device.config
        if cfg.get("flaky") and random.random() < 0.15:
            return DeviceReading(online=False)
        on = self._on.setdefault(device.id, bool(cfg.get("initially_on", True)))
        base = float(cfg.get("watts", device.nominal_watts or 60))
        standby = float(cfg.get("standby_watts", 0.4))
        state = self._state.setdefault(device.id, self._initial_state(cfg))
        if on:
            # Variação suave + ruído, para os gráficos parecerem com consumo real.
            wave = 1 + 0.12 * math.sin(time.time() / 90 + device.id)
            power = max(0.0, base * wave + random.uniform(-0.03, 0.03) * base)
            if "brightness" in state:
                power *= 0.2 + 0.8 * state["brightness"] / 100
        else:
            power = standby
        voltage = 127 + random.uniform(-2, 2)
        return DeviceReading(
            online=True,
            is_on=on,
            power_w=round(power, 1),
            voltage_v=round(voltage, 1),
            current_a=round(power / voltage, 3),
            state=dict(state),
        )

    async def set_state(self, device: DeviceRef, changes: dict[str, Any]) -> DeviceReading:
        state = self._state.setdefault(device.id, self._initial_state(device.config))
        state.update(changes)
        state["mode"] = "colour" if "color" in changes else "white"
        self._on[device.id] = True
        return await self.read(device)

    @staticmethod
    def _initial_state(config: dict[str, Any]) -> dict[str, Any]:
        caps = config.get("capabilities") or []
        state: dict[str, Any] = {}
        if BRIGHTNESS in caps:
            state.update(brightness=80, mode="white")
        if "color_temp" in caps:
            state["color_temp"] = 30
        if "color" in caps:
            state["color"] = {"h": 30, "s": 70, "v": 100}
        return state

    async def set_power(self, device: DeviceRef, on: bool) -> DeviceReading | None:
        self._on[device.id] = on
        return await self.read(device)

    def forget(self, device_id: int) -> None:
        self._on.pop(device_id, None)
        self._state.pop(device_id, None)
