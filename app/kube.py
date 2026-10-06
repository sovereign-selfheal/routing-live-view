"""A small Kubernetes API client with httpx: what the page needs and nothing more.

Everything runs with the ServiceAccount of the pod, except one call: before a label change the
page asks, with the token of the signed-in user (oauth-proxy `--pass-access-token`, scope
`user:check-access`), whether that user may patch the namespace (SelfSubjectAccessReview). So the
RBAC of the user decides; the ServiceAccount may patch only the demo namespaces.
"""

from __future__ import annotations

import os
import ssl
from collections.abc import AsyncIterator
from typing import Any

import httpx

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"


class KubeError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def api_base() -> str:
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    if not host:
        raise RuntimeError("KUBERNETES_SERVICE_HOST is not set (not in a pod?)")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    if ":" in host:  # IPv6
        host = f"[{host}]"
    return f"https://{host}:{port}"


class Kube:
    def __init__(self, base: str | None = None, sa_dir: str = SA_DIR,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base = base or api_base()
        self.sa_dir = sa_dir
        verify: Any = True
        ca = os.path.join(sa_dir, "ca.crt")
        if transport is None and os.path.exists(ca):
            verify = ssl.create_default_context(cafile=ca)
        self.client = httpx.AsyncClient(base_url=self.base, verify=verify, transport=transport,
                                        timeout=httpx.Timeout(10.0, read=None))

    def _sa_headers(self) -> dict[str, str]:
        with open(os.path.join(self.sa_dir, "token")) as fh:  # re-read: the token rotates
            return {"Authorization": f"Bearer {fh.read().strip()}"}

    async def close(self) -> None:
        await self.client.aclose()

    async def namespace_labels(self, names: list[str], label: str) -> dict[str, str | None]:
        """The value of `label` on each namespace; None when the namespace has no such label.

        A namespace that does not exist is left out.
        """
        out: dict[str, str | None] = {}
        for name in names:
            resp = await self.client.get(f"/api/v1/namespaces/{name}", headers=self._sa_headers(),
                                         timeout=10.0)
            if resp.status_code == 404:
                continue
            _raise_for(resp)
            labels = (resp.json().get("metadata") or {}).get("labels") or {}
            out[name] = labels.get(label)
        return out

    async def pods(self, namespace: str, selector: str) -> list[str]:
        resp = await self.client.get(f"/api/v1/namespaces/{namespace}/pods",
                                     params={"labelSelector": selector},
                                     headers=self._sa_headers(), timeout=10.0)
        _raise_for(resp)
        return sorted(
            item["metadata"]["name"] for item in resp.json().get("items") or []
            if (item.get("status") or {}).get("phase") == "Running")

    async def follow_log(self, namespace: str, pod: str, container: str,
                         since_time: str | None) -> AsyncIterator[str]:
        """Lines of the log of one container, with timestamps, until the stream ends."""
        params: dict[str, Any] = {"follow": "true", "timestamps": "true", "container": container}
        if since_time:
            params["sinceTime"] = since_time
        else:
            params["sinceSeconds"] = 1
        async with self.client.stream("GET", f"/api/v1/namespaces/{namespace}/pods/{pod}/log",
                                      params=params, headers=self._sa_headers()) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                _raise_for(resp)
            async for line in resp.aiter_lines():
                yield line

    async def user_can_patch_namespace(self, name: str, user_token: str) -> bool:
        """Whether the signed-in user may patch the namespace (SelfSubjectAccessReview)."""
        resp = await self.client.post(
            "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
            json={"apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
                  "spec": {"resourceAttributes": {"verb": "patch", "resource": "namespaces",
                                                  "name": name}}},
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=10.0,
        )
        _raise_for(resp)
        return bool((resp.json().get("status") or {}).get("allowed"))

    async def set_namespace_label(self, name: str, label: str, value: str) -> None:
        """Change one label of a namespace, with the ServiceAccount of the page."""
        headers = dict(self._sa_headers(), **{"Content-Type": "application/merge-patch+json"})
        resp = await self.client.patch(
            f"/api/v1/namespaces/{name}",
            json={"metadata": {"labels": {label: value}}},
            headers=headers,
            timeout=10.0,
        )
        _raise_for(resp)


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            message = resp.json().get("message") or resp.text
        except ValueError:
            message = resp.text
        raise KubeError(resp.status_code, str(message)[:300])
