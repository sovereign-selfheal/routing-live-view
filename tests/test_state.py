import asyncio

from app.state import LiveState


def ev(dest="local", restricted=()):
    return {"destination": dest, "ns_restricted": list(restricted), "namespaces": list(restricted)}


def test_counters_and_dedup():
    s = LiveState()
    assert s.add_decision(ev("local", ["payments"]), key=("p", "l1"))
    assert not s.add_decision(ev("local", ["payments"]), key=("p", "l1"))  # read twice
    s.add_decision(ev("external"))
    s.add_decision(ev("external", ["payments"]))
    assert s.counters == {"decisions": 3, "local": 1, "external": 2, "restricted": 2,
                          "restricted_external": 1}
    assert [e["seq"] for e in s.snapshot()["events"]] == [1, 2, 3]


async def test_wait_returns_new_events():
    s = LiveState()
    s.add_decision(ev())

    async def later():
        await asyncio.sleep(0.05)
        s.add_decision(ev("external"))

    task = asyncio.create_task(later())
    out = await s.wait_events(after=1, timeout=2)
    await task
    assert [e["seq"] for e in out["events"]] == [2]


async def test_wait_times_out_with_nothing_new():
    s = LiveState()
    out = await s.wait_events(after=0, timeout=0.05)
    assert out["events"] == [] and out["seq"] == 0


async def test_namespace_change_wakes_the_waiters():
    s = LiveState()

    async def later():
        await asyncio.sleep(0.05)
        s.set_namespaces({"payments": "public"})

    task = asyncio.create_task(later())
    out = await s.wait_events(after=0, timeout=2)
    await task
    assert out["namespaces"] == {"payments": "public"}
    assert out["seq"] == 1
