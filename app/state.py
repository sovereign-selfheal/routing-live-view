"""In-memory state of the page: recent decisions, counters and namespace labels.

Counters start when the pod starts. Browsers read the state with long polling
(`wait_events`): one request waits until a new event arrives or the timeout ends.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, deque
from typing import Any

RECENT = 200
DEDUP = 4000


class LiveState:
    def __init__(self) -> None:
        self.seq = 0
        self.started_at = time.time()
        self.events: deque[dict[str, Any]] = deque(maxlen=RECENT)
        self.namespaces: dict[str, str | None] = {}
        self.namespaces_error: str | None = None
        self.counters = {"decisions": 0, "local": 0, "external": 0, "restricted": 0,
                         "restricted_external": 0}
        self._seen: OrderedDict[tuple, None] = OrderedDict()
        self._changed = asyncio.Event()

    # -- writers --------------------------------------------------------------------
    def add_decision(self, event: dict[str, Any], key: tuple | None = None) -> bool:
        """Add one decision. A repeated key (log line read twice after a reconnect) is ignored."""
        if key is not None:
            if key in self._seen:
                return False
            self._seen[key] = None
            while len(self._seen) > DEDUP:
                self._seen.popitem(last=False)
        self.seq += 1
        event = dict(event, seq=self.seq)
        self.events.append(event)
        c = self.counters
        c["decisions"] += 1
        c[event["destination"]] = c.get(event["destination"], 0) + 1
        if event.get("ns_restricted"):
            c["restricted"] += 1
            if event["destination"] == "external":
                c["restricted_external"] += 1
        self._wake()
        return True

    def set_namespaces(self, labels: dict[str, str | None], error: str | None = None) -> None:
        if labels != self.namespaces or error != self.namespaces_error:
            self.namespaces = dict(labels)
            self.namespaces_error = error
            self.seq += 1
            self._wake()

    def _wake(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()

    # -- readers --------------------------------------------------------------------
    def snapshot(self, after: int = 0, limit: int = 30) -> dict[str, Any]:
        events = [e for e in self.events if e["seq"] > after][-limit:]
        return {
            "seq": self.seq,
            "started_at": self.started_at,
            "events": events,
            "namespaces": self.namespaces,
            "namespaces_error": self.namespaces_error,
            "counters": dict(self.counters),
        }

    async def wait_events(self, after: int, timeout: float) -> dict[str, Any]:
        """The state after `after`; waits up to `timeout` seconds when nothing is new."""
        if self.seq <= after:
            changed = self._changed
            try:
                await asyncio.wait_for(changed.wait(), timeout)
            except TimeoutError:
                pass
        return self.snapshot(after, limit=100)
