"""Contrato entre o núcleo e os adaptadores de protocolo.

O núcleo só conhece `DeviceReading` e `Adapter`; cada família de dispositivos (Tuya, Shelly,
simulador…) implementa essa interface. Adaptadores externos em outras linguagens poderão
falar o mesmo contrato via JSON-RPC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# Capacidades que um aparelho pode ter. A interface monta os controles a partir delas, então
# uma lâmpada, uma tomada ou um relé de qualquer marca aparecem do mesmo jeito.
POWER = "power"  # liga/desliga
ENERGY = "energy"  # mede potência e consumo
BRIGHTNESS = "brightness"  # brilho, 1 a 100 (%)
COLOR_TEMP = "color_temp"  # temperatura de cor, 0 (quente) a 100 (fria)
COLOR = "color"  # cor em HSV: h 0-360, s 0-100, v 0-100
CAPABILITIES = (POWER, ENERGY, BRIGHTNESS, COLOR_TEMP, COLOR)

# Chaves de `DeviceReading.state` e do comando de estado.
STATE_KEYS = (BRIGHTNESS, COLOR_TEMP, COLOR, "mode")


class AdapterError(Exception):
    """Falha de comunicação com o dispositivo, com mensagem pronta para o usuário."""


@dataclass
class DeviceReading:
    online: bool
    is_on: bool | None = None
    power_w: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    # Estado além do liga/desliga (brilho, cor…), com as chaves de STATE_KEYS.
    state: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceRef:
    id: int
    external_id: str | None
    config: dict[str, Any]
    nominal_watts: float | None = None


class Adapter(Protocol):
    name: str

    async def read(self, device: DeviceRef) -> DeviceReading: ...

    async def set_power(self, device: DeviceRef, on: bool) -> DeviceReading | None: ...

    def forget(self, device_id: int) -> None: ...

    # Opcional: `capabilities(config) -> list[str]`. Sem ele, o aparelho só liga e desliga.


class StateAdapter(Adapter, Protocol):
    """Adaptadores de aparelhos com estado além do liga/desliga (lâmpadas, por exemplo)."""

    async def set_state(self, device: DeviceRef, changes: dict[str, Any]) -> DeviceReading | None:
        """Aplica `changes` (chaves de STATE_KEYS, já validadas pelo núcleo)."""
        ...


def adapter_capabilities(adapter: Any, config: dict[str, Any]) -> list[str]:
    """Capacidades de um aparelho segundo o seu adaptador (só liga/desliga por padrão)."""
    method = getattr(adapter, "capabilities", None)
    return list(method(config)) if method else [POWER]
