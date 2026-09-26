"""Mapeamento dos data points (DPs) Tuya para as capacidades do Cordyhome.

A nuvem Tuya descreve cada DP com um código (`cur_power`, `switch_1`…) e uma especificação
com escala e unidade. Guardamos esse mapa junto do dispositivo para ler tudo localmente.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

SWITCH_CODES = ("switch_1", "switch", "switch_led", "switch_usb1")
POWER_CODES = ("cur_power", "power")
VOLTAGE_CODES = ("cur_voltage", "voltage")
CURRENT_CODES = ("cur_current", "current")


@dataclass
class DpSpec:
    dp: int
    scale: int = 0
    unit: str = ""

    def convert(self, value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return value / (10**self.scale)


@dataclass
class DpMap:
    switch: int = 1
    power: DpSpec | None = None
    voltage: DpSpec | None = None
    current: DpSpec | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DpMap:
        if not data:
            return default_dp_map()

        def spec(key: str) -> DpSpec | None:
            value = data.get(key)
            return DpSpec(**value) if value else None

        return cls(
            switch=int(data.get("switch", 1)),
            power=spec("power"),
            voltage=spec("voltage"),
            current=spec("current"),
        )

    @property
    def energy_dps(self) -> list[int]:
        return [s.dp for s in (self.power, self.voltage, self.current) if s]


def default_dp_map() -> DpMap:
    """Layout mais comum em tomadas Tuya com medição (usado se a nuvem não informar)."""
    return DpMap(
        switch=1,
        current=DpSpec(dp=18, scale=0, unit="mA"),
        power=DpSpec(dp=19, scale=1, unit="W"),
        voltage=DpSpec(dp=20, scale=1, unit="V"),
    )


def _value_desc(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def dp_map_from_strategy(local_strategy: dict[Any, dict[str, Any]] | None) -> DpMap | None:
    """Monta o mapa a partir de `local_strategy` do SDK de compartilhamento da Tuya."""
    if not local_strategy:
        return None
    by_code: dict[str, tuple[int, dict[str, Any]]] = {}
    for dp_id, info in local_strategy.items():
        code = info.get("status_code")
        if not code:
            continue
        desc = _value_desc((info.get("config_item") or {}).get("valueDesc"))
        by_code[code] = (int(dp_id), desc)

    def find(codes: tuple[str, ...]) -> tuple[int, dict[str, Any]] | None:
        return next((by_code[c] for c in codes if c in by_code), None)

    def spec(codes: tuple[str, ...], default_unit: str) -> DpSpec | None:
        found = find(codes)
        if not found:
            return None
        dp, desc = found
        return DpSpec(dp=dp, scale=int(desc.get("scale", 0)), unit=desc.get("unit") or default_unit)

    switch = find(SWITCH_CODES)
    return DpMap(
        switch=switch[0] if switch else 1,
        power=spec(POWER_CODES, "W"),
        voltage=spec(VOLTAGE_CODES, "V"),
        current=spec(CURRENT_CODES, "mA"),
    )


def parse_dps(dps: dict[str, Any], mapping: DpMap) -> dict[str, Any]:
    """Converte o dicionário bruto de DPs em valores com unidade do Cordyhome."""
    out: dict[str, Any] = {}
    switch = dps.get(str(mapping.switch))
    if isinstance(switch, bool):
        out["is_on"] = switch
    if mapping.power and str(mapping.power.dp) in dps:
        out["power_w"] = mapping.power.convert(dps[str(mapping.power.dp)])
    if mapping.voltage and str(mapping.voltage.dp) in dps:
        out["voltage_v"] = mapping.voltage.convert(dps[str(mapping.voltage.dp)])
    if mapping.current and str(mapping.current.dp) in dps:
        amps = mapping.current.convert(dps[str(mapping.current.dp)])
        if amps is not None and mapping.current.unit.lower() == "ma":
            amps /= 1000
        out["current_a"] = amps
    return out
