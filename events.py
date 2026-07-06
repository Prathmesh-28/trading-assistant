"""Tiny asyncio pub/sub so the web dashboard (and anything else) can subscribe
to engine activity without the engine knowing subscribers exist. Telegram stays
wired up separately in notifier.py — this is purely for the live dashboard."""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, event_type: str, data: Any = None) -> None:
        event = {"type": event_type, "data": data}
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # a slow/stalled client shouldn't build unbounded backlog or
                # block the engine — drop the oldest and keep going
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
