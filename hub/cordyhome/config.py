from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_web_dir() -> Path | None:
    # Desenvolvimento: build do SvelteKit em ../web/build. Docker: copiado para /app/web.
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "web" / "build",
        Path("/app/web"),
    ]
    return next((p for p in candidates if (p / "index.html").exists()), None)


@dataclass(frozen=True)
class Config:
    data_dir: Path
    host: str
    port: int
    web_dir: Path | None
    demo: bool

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cordyhome.db"

    @classmethod
    def from_env(cls) -> Config:
        web = os.environ.get("CORDYHOME_WEB")
        return cls(
            data_dir=Path(os.environ.get("CORDYHOME_DATA", Path.home() / ".cordyhome")),
            host=os.environ.get("CORDYHOME_HOST", "0.0.0.0"),
            port=int(os.environ.get("CORDYHOME_PORT", "8420")),
            web_dir=Path(web) if web else _default_web_dir(),
            demo=_env_bool("CORDYHOME_DEMO"),
        )
