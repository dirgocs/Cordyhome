"""Usuários locais, senhas com scrypt e sessões por cookie."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from .db import Database

SESSION_COOKIE = "cordy_session"
SESSION_TTL = 60 * 60 * 24 * 30

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    b64 = base64.b64encode
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db: Database):
        self.db = db
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def has_users(self) -> bool:
        return bool(self.db.scalar("SELECT EXISTS (SELECT 1 FROM users)"))

    def create_user(self, username: str, password: str) -> int:
        cur = self.db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username.strip(), hash_password(password), int(time.time())),
        )
        return int(cur.lastrowid)

    def authenticate(self, username: str, password: str) -> int | None:
        row = self.db.one(
            "SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)
        )
        if row is None:
            # Mesmo custo de uma verificação real para não revelar quais usuários existem.
            verify_password(password, hash_password("x"))
            return None
        return row["id"] if verify_password(password, row["password_hash"]) else None

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        self.db.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (_token_hash(token), user_id, now, now + SESSION_TTL),
        )
        self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        return token

    def user_for_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        row = self.db.one(
            "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (_token_hash(token), int(time.time())),
        )
        return dict(row) if row else None

    def revoke(self, token: str | None) -> None:
        if token:
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # Limite simples de tentativas de login por IP: 5 falhas a cada 5 minutos.
    def is_rate_limited(self, key: str, limit: int = 5, window: float = 300) -> bool:
        attempts = self._failures[key]
        cutoff = time.monotonic() - window
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return len(attempts) >= limit

    def record_failure(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def clear_failures(self, key: str) -> None:
        self._failures.pop(key, None)
