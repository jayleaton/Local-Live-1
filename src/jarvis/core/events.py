from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Callable


class CancelledError(Exception):
    """Raised when a cancellation token is tripped."""


class CancelToken:
    """Cooperative cancellation that propagates across the whole turn.

    Barge-in must cancel TTS, LLM generation, *and* in-flight tool calls.
    This token is the single signal shared by every stage.
    """

    def __init__(self) -> None:
        self._cancelled = False
        self._callbacks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                pass

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise CancelledError()

    def on_cancel(self, cb: Callable[[], None]) -> Callable[[], None]:
        if self._cancelled:
            cb()
        else:
            self._callbacks.append(cb)

        def _unsub() -> None:
            try:
                self._callbacks.remove(cb)
            except ValueError:
                pass

        return _unsub


class EventBus:
    """Tiny async pub/sub used for audit/telemetry and UI hooks."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[dict[str, Any]], Any]]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
        self._subs[topic].append(handler)

        def _unsub() -> None:
            try:
                self._subs[topic].remove(handler)
            except ValueError:
                pass

        return _unsub

    async def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {}
        for handler in list(self._subs.get(topic, [])) + list(self._subs.get("*", [])):
            result = handler({"topic": topic, **payload})
            if asyncio.iscoroutine(result):
                await result


class AuditLog:
    def __init__(self, sink: Callable[[Any], None] | None = None) -> None:
        self.entries: list[Any] = []
        self._sink = sink

    def add(self, event: str, **detail: Any) -> None:
        from jarvis.core.types import AuditEntry

        entry = AuditEntry(ts=time.time(), kind=event, detail=detail)
        self.entries.append(entry)
        if self._sink:
            self._sink(entry)
