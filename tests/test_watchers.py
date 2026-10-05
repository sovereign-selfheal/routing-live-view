import asyncio

from app.config import Settings
from app.state import LiveState
from app.watchers import follow_pod, follow_router, poll_namespaces

TS1 = "2026-10-05T18:00:01.000000001Z"
TS2 = "2026-10-05T18:00:02.000000001Z"
DEC = ("[policy-router] {'policy': 'chain', 'requested': 'auto', 'routed_to': 'local-fast', "
       "'decided_by': 'efficiency', 'chain': [], 'reason': 'x', 'team': 'agents'}")


class FakeKube:
    def __init__(self):
        self.since = []
        self.pod_sets = [["litellm-a"], ["litellm-a", "litellm-b"], ["litellm-b"]]

    async def follow_log(self, namespace, pod, container, since_time):
        self.since.append(since_time)
        # Every connection returns the same two lines, then ends (like a log rotation).
        for line in (f"{TS1} {DEC}", f"{TS2} other line"):
            yield line
        await asyncio.sleep(0)

    async def pods(self, namespace, selector):
        return self.pod_sets.pop(0) if len(self.pod_sets) > 1 else self.pod_sets[0]

    async def namespace_labels(self, names, label):
        return {"payments": "restricted"}


async def run_for(coro, seconds):
    task = asyncio.create_task(coro)
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_follow_pod_reconnects_from_the_last_timestamp(monkeypatch):
    kube, state = FakeKube(), LiveState()
    monkeypatch.setattr("app.watchers.RECONNECT_SECONDS", 0.01)
    await run_for(follow_pod(kube, Settings(kubernetes_enabled=False), state, "litellm-a"), 0.1)
    assert kube.since[0] is None and kube.since[1] == TS2
    assert state.counters["decisions"] == 1  # the same line read again is counted once


async def test_follow_router_tracks_the_pods():
    kube, state = FakeKube(), LiveState()
    settings = Settings(kubernetes_enabled=False, pod_poll_seconds=0.02)
    await run_for(follow_router(kube, settings, state), 0.15)
    assert {e["pod"] for e in state.events} == {"litellm-a", "litellm-b"}


async def test_poll_namespaces():
    state, wake = LiveState(), asyncio.Event()
    settings = Settings(kubernetes_enabled=False, namespace_poll_seconds=0.02)
    await run_for(poll_namespaces(FakeKube(), settings, state, wake), 0.05)
    assert state.namespaces == {"payments": "restricted"}
