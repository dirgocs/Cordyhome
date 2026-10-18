"""Mapeamento dos data points (DPs) Tuya para as capacidades do Cordyhome.

A nuvem Tuya descreve cada DP com um código (`cur_power`, `switch_1`…) e uma especificação
com escala e unidade. Guardamos esse mapa junto do dispositivo para ler tudo localmente.
"""

from __future__ import annotations

import colorsys
import json
from dataclasses import asdict, dataclass
from typing import Any

from ..base import BRIGHTNESS, COLOR, COLOR_TEMP, ENERGY, POWER

SWITCH_CODES = ("switch_1", "switch", "switch_led", "switch_usb1")
POWER_CODES = ("cur_power", "power")
VOLTAGE_CODES = ("cur_voltage", "voltage")
CURRENT_CODES = ("cur_current", "current")
# Lâmpadas: os códigos "_v2" usam 0-1000 e a cor em HSV; os antigos usam 0-255 e RGB+HSV.
MODE_CODES = ("work_mode",)
BRIGHTNESS_CODES = ("bright_value_v2", "bright_value")
TEMP_CODES = ("temp_value_v2", "temp_value")
COLOUR_CODES = ("colour_data_v2", "colour_data")


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
class DpRange:
    """DP numérico com faixa própria, convertido de/para 0-100 (%)."""

    dp: int
    min: int
    max: int

    def to_percent(self, value: Any) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int | float) or self.max <= self.min:
            return None
        return round((min(max(value, self.min), self.max) - self.min) * 100 / (self.max - self.min))

    def from_percent(self, percent: int) -> int:
        return round(self.min + (self.max - self.min) * percent / 100)


@dataclass
class DpColour:
    dp: int
    v2: bool = True  # "hhhhssssvvvv" (s e v 0-1000); senão "rrggbbhhhhssvv" (s e v 0-255)

    def parse(self, value: Any) -> dict[str, int] | None:
        if not isinstance(value, str):
            return None
        try:
            if self.v2 and len(value) == 12:
                h, s, v = int(value[0:4], 16), int(value[4:8], 16), int(value[8:12], 16)
                return {"h": h % 361, "s": round(s / 10), "v": round(v / 10)}
            if not self.v2 and len(value) == 14:
                h, s, v = int(value[6:10], 16), int(value[10:12], 16), int(value[12:14], 16)
                return {"h": h % 361, "s": round(s * 100 / 255), "v": round(v * 100 / 255)}
        except ValueError:
            return None
        return None

    def encode(self, color: dict[str, int]) -> str:
        h, s, v = color["h"], color["s"], color["v"]
        if self.v2:
            return f"{h:04x}{s * 10:04x}{v * 10:04x}"
        rgb = "".join(
            f"{round(c * 255):02x}" for c in colorsys.hsv_to_rgb(h / 360, s / 100, v / 100)
        )
        return f"{rgb}{h:04x}{round(s * 255 / 100):02x}{round(v * 255 / 100):02x}"


@dataclass
class DpMap:
    switch: int = 1
    power: DpSpec | None = None
    voltage: DpSpec | None = None
    current: DpSpec | None = None
    mode: int | None = None
    brightness: DpRange | None = None
    color_temp: DpRange | None = None
    colour: DpColour | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DpMap:
        if not data:
            return default_dp_map()

        def build(key: str, kind: type) -> Any:
            value = data.get(key)
            return kind(**value) if value else None

        return cls(
            switch=int(data.get("switch", 1)),
            power=build("power", DpSpec),
            voltage=build("voltage", DpSpec),
            current=build("current", DpSpec),
            mode=data.get("mode"),
            brightness=build("brightness", DpRange),
            color_temp=build("color_temp", DpRange),
            colour=build("colour", DpColour),
        )

    @property
    def energy_dps(self) -> list[int]:
        return [s.dp for s in (self.power, self.voltage, self.current) if s]

    @property
    def capabilities(self) -> list[str]:
        caps = [POWER]
        if self.power:
            caps.append(ENERGY)
        if self.brightness:
            caps.append(BRIGHTNESS)
        if self.color_temp:
            caps.append(COLOR_TEMP)
        if self.colour:
            caps.append(COLOR)
        return caps

    def state_dps(self, changes: dict[str, Any]) -> dict[str, Any]:
        """DPs que aplicam um comando de estado (e acendem a lâmpada junto)."""
        dps: dict[str, Any] = {str(self.switch): True}
        mode = None
        if "brightness" in changes and self.brightness:
            dps[str(self.brightness.dp)] = self.brightness.from_percent(changes["brightness"])
            mode = "white"
        if "color_temp" in changes and self.color_temp:
            dps[str(self.color_temp.dp)] = self.color_temp.from_percent(changes["color_temp"])
            mode = "white"
        if "color" in changes and self.colour:
            dps[str(self.colour.dp)] = self.colour.encode(changes["color"])
            mode = "colour"
        if mode and self.mode is not None:
            dps[str(self.mode)] = mode
        return dps


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

    def value_range(codes: tuple[str, ...], defaults: dict[str, tuple[int, int]]) -> DpRange | None:
        code = next((c for c in codes if c in by_code), None)
        if code is None:
            return None
        dp, desc = by_code[code]
        lo, hi = defaults[code]
        return DpRange(dp=dp, min=int(desc.get("min", lo)), max=int(desc.get("max", hi)))

    switch = find(SWITCH_CODES)
    mode = find(MODE_CODES)
    colour_code = next((c for c in COLOUR_CODES if c in by_code), None)
    return DpMap(
        switch=switch[0] if switch else 1,
        power=spec(POWER_CODES, "W"),
        voltage=spec(VOLTAGE_CODES, "V"),
        current=spec(CURRENT_CODES, "mA"),
        mode=mode[0] if mode else None,
        brightness=value_range(
            BRIGHTNESS_CODES, {"bright_value_v2": (10, 1000), "bright_value": (25, 255)}
        ),
        color_temp=value_range(TEMP_CODES, {"temp_value_v2": (0, 1000), "temp_value": (0, 255)}),
        colour=(
            DpColour(dp=by_code[colour_code][0], v2=colour_code.endswith("_v2"))
            if colour_code
            else None
        ),
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
    state: dict[str, Any] = {}
    if mapping.mode is not None and isinstance(dps.get(str(mapping.mode)), str):
        state["mode"] = dps[str(mapping.mode)]
    if mapping.brightness and str(mapping.brightness.dp) in dps:
        state["brightness"] = mapping.brightness.to_percent(dps[str(mapping.brightness.dp)])
    if mapping.color_temp and str(mapping.color_temp.dp) in dps:
        state["color_temp"] = mapping.color_temp.to_percent(dps[str(mapping.color_temp.dp)])
    if mapping.colour and str(mapping.colour.dp) in dps:
        state["color"] = mapping.colour.parse(dps[str(mapping.colour.dp)])
    state = {k: v for k, v in state.items() if v is not None}
    if state:
        out["state"] = state
    return out
