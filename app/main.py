"""routing-live-view: a live page of the routing decisions of the sovereign self-heal demo.

The page shows, while it happens, where each LLM request of the agents goes (local GPU or the
external model), and the data-class label of the demo namespaces. A request about a restricted
namespace stays in the cluster (router v0.11.0, namespace policy).
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.config import Settings
from app.kube import Kube, KubeError
from app.state import LiveState
from app.watchers import follow_router, poll_namespaces

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("routing-live-view")

STATIC = Path(__file__).parent / "static"
ALLOWED_VALUES = ("restricted", "public")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = getattr(app.state, "settings", None) or Settings.from_env()
    app.state.settings = settings
    app.state.live = LiveState()
    app.state.wake = asyncio.Event()
    tasks: list[asyncio.Task] = []
    kube = getattr(app.state, "kube", None)
    if settings.kubernetes_enabled:
        kube = kube or Kube()
        app.state.kube = kube
        tasks = [
            asyncio.create_task(poll_namespaces(kube, settings, app.state.live, app.state.wake)),
            asyncio.create_task(follow_router(kube, settings, app.state.live)),
        ]
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task
    if kube is not None and settings.kubernetes_enabled:
        await kube.close()


app = FastAPI(title="routing-live-view", lifespan=lifespan)


class DataClass(BaseModel):
    value: str


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/config")
async def config(request: Request,
                 x_forwarded_user: str | None = Header(default=None)) -> dict:
    s: Settings = request.app.state.settings
    return {
        "cluster_name": s.cluster_name,
        "label": s.data_class_label,
        "demo_namespaces": s.demo_namespaces,
        "local_model": s.local_model_label,
        "sota_model": s.sota_model_label,
        "user": x_forwarded_user,
    }


@app.get("/api/state")
async def state(request: Request) -> dict:
    return request.app.state.live.snapshot()


@app.get("/api/events")
async def events(request: Request, after: int = 0, timeout: float = 20.0) -> dict:
    timeout = max(0.0, min(timeout, 25.0))  # below the 30 s of the OpenShift router
    return await request.app.state.live.wait_events(after, timeout)


@app.post("/api/namespaces/{name}/data-class")
async def set_data_class(
    name: str,
    body: DataClass,
    request: Request,
    x_forwarded_access_token: str | None = Header(default=None),
    x_forwarded_user: str | None = Header(default=None),
) -> JSONResponse:
    s: Settings = request.app.state.settings
    if name not in s.demo_namespaces:
        return JSONResponse({"error": f"{name} is not a namespace of this page."}, status_code=404)
    if body.value not in ALLOWED_VALUES:
        return JSONResponse({"error": "The value must be restricted or public."}, status_code=400)
    if not x_forwarded_access_token:
        return JSONResponse({"error": "Sign in with OpenShift to change a label."},
                            status_code=401)
    kube: Kube | None = getattr(request.app.state, "kube", None)
    if kube is None:
        return JSONResponse({"error": "The Kubernetes API is off."}, status_code=503)
    try:
        await kube.set_namespace_label(name, s.data_class_label, body.value,
                                       x_forwarded_access_token)
    except KubeError as exc:
        logger.warning("label %s=%s on %s by %s: %s", s.data_class_label, body.value, name,
                       x_forwarded_user, exc)
        if exc.status == 403:
            return JSONResponse({"error": "Your OpenShift user cannot change this namespace."},
                                status_code=403)
        return JSONResponse({"error": str(exc)}, status_code=502)
    logger.info("label %s=%s on %s by %s", s.data_class_label, body.value, name, x_forwarded_user)
    request.app.state.wake.set()  # read the labels again now
    return JSONResponse({"namespace": name, "value": body.value})
