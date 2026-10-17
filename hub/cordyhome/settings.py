from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from .db import Database


class Settings(BaseModel):
    tariff_per_kwh: float = Field(0.85, ge=0, le=100)
    timezone: str = "America/Sao_Paulo"
    poll_interval_sec: int = Field(10, ge=3, le=300)
    offline_after_failures: int = Field(3, ge=1, le=20)


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
