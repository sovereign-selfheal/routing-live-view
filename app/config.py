"""Settings from the environment (set by the gitops component routing-live-view)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


def _list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _labels(value: str) -> dict[str, str]:
    """A JSON object of tier -> name; anything else is logged and ignored."""
    if not value.strip():
        return {}
    try:
        data = json.loads(value)
    except ValueError:
        log.warning("TIER_LABELS is not valid JSON: ignored")
        return {}
    if not isinstance(data, dict):
        log.warning("TIER_LABELS is not a JSON object: ignored")
        return {}
    return {str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}


@dataclass(frozen=True)
class Settings:
    # Namespaces shown as cards, in this order. Only these can be changed from the page.
    demo_namespaces: list[str] = field(default_factory=lambda: ["agentic-triage", "payments"])
    # Label of the namespace policy of the router (router v0.11.0).
    data_class_label: str = "sovereign-selfheal.io/data-class"
    # Where the router runs: the page follows the logs of these pods.
    router_namespace: str = "maas-routing"
    router_pod_selector: str = "app=litellm"
    router_container: str = "litellm"
    # Model aliases of the router (chain.yaml): the SOTA alias means "outside the cluster".
    sota_alias: str = "sota-smart"
    # Texts of the page.
    cluster_name: str = ""
    local_model_label: str = "Local model"
    sota_model_label: str = "External model"
    # Name of the agent (or application) of each API-key tier, shown in the column Agent. The router
    # logs the tier of each request (`team`); a tier without a name shows as "<tier> key".
    tier_labels: dict[str, str] = field(default_factory=dict)
    # Seconds between two reads of the namespace labels and of the router pods.
    namespace_poll_seconds: float = 2.0
    pod_poll_seconds: float = 10.0
    # Off in the unit tests: no Kubernetes API calls.
    kubernetes_enabled: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            demo_namespaces=_list(env("DEMO_NAMESPACES", "agentic-triage,payments")),
            data_class_label=env("DATA_CLASS_LABEL", cls.data_class_label),
            router_namespace=env("ROUTER_NAMESPACE", cls.router_namespace),
            router_pod_selector=env("ROUTER_POD_SELECTOR", cls.router_pod_selector),
            router_container=env("ROUTER_CONTAINER", cls.router_container),
            sota_alias=env("SOTA_ALIAS", cls.sota_alias),
            cluster_name=env("CLUSTER_NAME", ""),
            local_model_label=env("LOCAL_MODEL_LABEL", cls.local_model_label),
            sota_model_label=env("SOTA_MODEL_LABEL", cls.sota_model_label),
            tier_labels=_labels(env("TIER_LABELS", "")),
            namespace_poll_seconds=float(env("NAMESPACE_POLL_SECONDS", "2")),
            pod_poll_seconds=float(env("POD_POLL_SECONDS", "10")),
            kubernetes_enabled=env("KUBERNETES_ENABLED", "true").lower() in ("1", "true", "yes"),
        )
