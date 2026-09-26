"""Acesso ao SQLite.

O hub usa uma única conexão compartilhada. Todas as escritas acontecem na thread do event
loop; as chamadas bloqueantes aos dispositivos rodam em threads separadas e nunca tocam no
banco diretamente.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

MIGRATIONS: list[str] = [
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );

    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    );

    CREATE TABLE rooms (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    );

    CREATE TABLE devices (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
        kind TEXT NOT NULL DEFAULT 'plug',
        adapter TEXT NOT NULL,
        external_id TEXT,
        config TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0,
        nominal_watts REAL,
        power_alert_watts REAL,
        online INTEGER NOT NULL DEFAULT 0,
        is_on INTEGER,
        power_w REAL,
        voltage_v REAL,
        current_a REAL,
        last_seen INTEGER,
        last_error TEXT,
        fail_count INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        UNIQUE (adapter, external_id)
    );

    CREATE TABLE energy_minute (
        device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        ts INTEGER NOT NULL,
        wh REAL NOT NULL,
        avg_w REAL NOT NULL,
        max_w REAL NOT NULL,
        PRIMARY KEY (device_id, ts)
    );
    CREATE INDEX idx_energy_minute_ts ON energy_minute(ts);

    CREATE TABLE energy_hour (
        device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        ts INTEGER NOT NULL,
        wh REAL NOT NULL,
        PRIMARY KEY (device_id, ts)
    );
    CREATE INDEX idx_energy_hour_ts ON energy_hour(ts);

    CREATE TABLE schedules (
        id INTEGER PRIMARY KEY,
        device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        action TEXT NOT NULL,
        time TEXT NOT NULL,
        days INTEGER NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        last_run_key TEXT,
        last_run_at INTEGER,
        last_result TEXT,
        created_at INTEGER NOT NULL
    );

    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY,
        device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        severity TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        resolved_at INTEGER,
        acknowledged_at INTEGER
    );
    CREATE INDEX idx_alerts_open ON alerts(resolved_at, acknowledged_at);

    CREATE TABLE events (
        id INTEGER PRIMARY KEY,
        device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        ts INTEGER NOT NULL,
        source TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT
    );
    CREATE INDEX idx_events_device_ts ON events(device_id, ts);

    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
]


class Database:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        for index in range(version, len(MIGRATIONS)):
            with self.transaction():
                for statement in _split_sql(MIGRATIONS[index]):
                    self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {index + 1}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def execute(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, rows)

    def one(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def all(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def scalar(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> Any:
        row = self.one(sql, params)
        return None if row is None else row[0]

    def close(self) -> None:
        self._conn.close()


def _split_sql(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]
