"""Background tasks: namespace labels and the decision lines of the router pods."""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.decisions import parse_line, split_timestamp
from app.kube import Kube
from app.state import LiveState

logger = logging.getLogger(__name__)

# Wait before the follower of a pod connects again (stream end, API error).
RECONNECT_SECONDS = 2.0


async def poll_namespaces(kube: Kube, settings: Settings, state: LiveState,
                          wake: asyncio.Event) -> None:
    """Read the labels of the demo namespaces every few seconds, or at once when woken."""
    while True:
        try:
            labels = await kube.namespace_labels(settings.demo_namespaces,
                                                 settings.data_class_label)
            state.set_namespaces(labels)
        except Exception as exc:  # keep the last labels, show the error
            logger.warning("namespace labels: %s", exc)
            state.set_namespaces(state.namespaces, error=f"{type(exc).__name__}: {exc}"[:200])
        try:
            await asyncio.wait_for(wake.wait(), settings.namespace_poll_seconds)
        except TimeoutError:
            pass
        wake.clear()


async def follow_pod(kube: Kube, settings: Settings, state: LiveState, pod: str) -> None:
    """Follow the log of one router pod; reconnect from the last timestamp when it ends."""
    since: str | None = None
    while True:
        try:
            async for line in kube.follow_log(settings.router_namespace, pod,
                                              settings.router_container, since):
                ts, _text = split_timestamp(line)
                if ts:
                    since = ts
                event = parse_line(line, settings.sota_alias)
                if event is not None:
                    state.add_decision(dict(event, pod=pod), key=(pod, line))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("log of %s: %s", pod, exc)
        await asyncio.sleep(RECONNECT_SECONDS)


async def follow_router(kube: Kube, settings: Settings, state: LiveState) -> None:
    """Keep one follower per running router pod (replicas come and go)."""
    tasks: dict[str, asyncio.Task] = {}
    try:
        while True:
            try:
                pods = set(await kube.pods(settings.router_namespace,
                                           settings.router_pod_selector))
                for pod in pods - set(tasks):
                    logger.info("following router pod %s", pod)
                    tasks[pod] = asyncio.create_task(follow_pod(kube, settings, state, pod))
                for pod in set(tasks) - pods:
                    logger.info("router pod %s is gone", pod)
                    tasks.pop(pod).cancel()
            except Exception as exc:
                logger.warning("router pods: %s", exc)
            await asyncio.sleep(settings.pod_poll_seconds)
    finally:
        for task in tasks.values():
            task.cancel()
