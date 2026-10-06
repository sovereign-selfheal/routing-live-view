"""Settings from the environment (set by the gitops component routing-live-view)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
            namespace_poll_seconds=float(env("NAMESPACE_POLL_SECONDS", "2")),
            pod_poll_seconds=float(env("POD_POLL_SECONDS", "10")),
            kubernetes_enabled=env("KUBERNETES_ENABLED", "true").lower() in ("1", "true", "yes"),
        )
