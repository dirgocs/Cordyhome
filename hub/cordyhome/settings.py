from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .adapters.tuya.discovery import MAX_NETWORKS, normalize_network
from .db import Database


def normalize_networks(values: list[str]) -> list[str]:
    """Faixas de IP onde procurar as tomadas, validadas e sem repetição."""
    out: list[str] = []
    for value in values:
        if value.strip() and (network := normalize_network(value)) not in out:
            out.append(network)
    if len(out) > MAX_NETWORKS:
        raise ValueError(f"Informe no máximo {MAX_NETWORKS} faixas de rede.")
    return out


class Settings(BaseModel):
    tariff_per_kwh: float = Field(0.85, ge=0, le=100)
    timezone: str = "America/Sao_Paulo"
    poll_interval_sec: int = Field(10, ge=3, le=300)
    offline_after_failures: int = Field(3, ge=1, le=20)
    # Redes (VLANs) das tomadas que o broadcast não alcança, ex.: ["192.168.20.0/24"].
    lan_networks: list[str] = Field(default_factory=list)

    @field_validator("lan_networks")
    @classmethod
    def valid_networks(cls, value: list[str]) -> list[str]:
        return normalize_networks(value)


class SettingsStore:
    """Configurações do usuário (tabela chave/valor) e segredos de integrações."""

    def __init__(self, db: Database):
        self.db = db

    def get(self) -> Settings:
        rows = self.db.all("SELECT key, value FROM settings WHERE key NOT LIKE '%.%'")
        data = {row["key"]: json.loads(row["value"]) for row in rows}
        return Settings(**{k: v for k, v in data.items() if k in Settings.model_fields})

    def update(self, changes: dict[str, Any]) -> Settings:
        merged = self.get().model_copy(update=changes)
        validated = Settings(**merged.model_dump())
        with self.db.transaction():
            for key, value in validated.model_dump().items():
                self._put(key, value)
        return validated

    def get_json(self, key: str) -> Any:
        raw = self.db.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return None if raw is None else json.loads(raw)

    def set_json(self, key: str, value: Any) -> None:
        if value is None:
            self.db.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            self._put(key, value)

    def _put(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
