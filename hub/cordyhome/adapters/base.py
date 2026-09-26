"""Contrato entre o núcleo e os adaptadores de protocolo.

O núcleo só conhece `DeviceReading` e `Adapter`; cada família de dispositivos (Tuya, Shelly,
simulador…) implementa essa interface. Adaptadores externos em outras linguagens poderão
falar o mesmo contrato via JSON-RPC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class AdapterError(Exception):
    """Falha de comunicação com o dispositivo, com mensagem pronta para o usuário."""


@dataclass
class DeviceReading:
    online: bool
    is_on: bool | None = None
    power_w: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
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
