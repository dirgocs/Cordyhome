"""Barramento de eventos em memória que alimenta o WebSocket da interface."""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, type_: str, **payload: Any) -> None:
        message = {"type": type_, **payload}
        for queue in list(self._subscribers):
            if queue.full():
                # Cliente lento: descarta o mais antigo em vez de travar o hub.
                queue.get_nowait()
            queue.put_nowait(message)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)
