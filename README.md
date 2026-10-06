# routing-live-view: live page of the routing decisions

A web page for the demo *Sovereign Self-Healing: LLM Routing and AI SRE Triage on OpenShift AI*. It shows,
while it happens, where each LLM request of the agents goes: the **local GPU** in the cluster or the
**external SOTA model**. It also shows the data-class label of the demo namespaces and lets a signed-in
user change it. A request about a namespace labelled `sovereign-selfheal.io/data-class=restricted` stays on
the local model (router v0.11.0, namespace policy), and the page proves it: the counter "Restricted requests
sent outside the cluster" stays at **0**.

Read [`AGENTS.md`](AGENTS.md) before changing anything.

## What the page shows

- **Namespaces**: one card per demo namespace (`DEMO_NAMESPACES`) with its label: `restricted` (red),
  `public` or no label (normal routing). A button changes the label, and the card shows the `oc label`
  command that does the same from a terminal.
- **Request flow**: each decision of the router moves from the namespace of the request, through the
  agents and the router (the gate that decided lights up), to the local GPU or out of the cluster.
- **Decisions**: the last decisions, with the agent that asked, the namespaces of the request and a
  small tag that says how the router found them (`hint` from the agent, `scan` of the text), the gate or
  policy that decided and the destination. A dash means that the request names no namespace.
  - **Agent**: the name of the agent of the API-key tier (the router logs the tier as `team`, from the
    header `x-team` that the gateway sets from the key; `TIER_LABELS`). A tier without a name shows as
    `<tier> key`, for example `research key` (a key of people, not of an agent).
  - **SOTA budget** (router v0.12.0): for a tier with a budget, a tag such as `SOTA 25k/30k` (tokens of
    the SOTA model in the window / budget). It is red when the budget is used: the router then keeps
    the requests of the tier on the local model.
- **Counters** since the pod started: restricted requests, kept in the cluster, sent outside, and the
  restricted requests sent outside (must stay 0).

The page reads metadata only: the router's decision line has no prompt text. It loads no font or script
from the internet.

## How it works

| Data | Source | Permission (ServiceAccount of the page) |
|---|---|---|
| Decisions | The log lines `[policy-router] {...}` of the LiteLLM pods (follow, one stream per replica, reconnect from the last timestamp). The line is a stable interface of the router repo | `get`/`list` pods and `get` pods/log in the router namespace (Role in the gitops repo) |
| Labels | `GET` of each demo namespace every 2 seconds, and at once after a change from the page | `get` namespaces (ClusterRole `sovereign-selfheal-namespace-reader`, bound by the ansible repo) |
| Label change | First a `SelfSubjectAccessReview` with the **token of the signed-in user** (`X-Forwarded-Access-Token` of oauth-proxy, scope `user:check-access`): may this user patch the namespace? Only if yes, `PATCH` of the namespace label | `patch` on the demo namespaces only (ClusterRole with `resourceNames`, bound by the ansible repo). The RBAC of the user decides; the page changes only the demo namespaces and only to `restricted` or `public`, and logs the user |

Browsers use long polling (`GET /api/events?after=<seq>`, at most 25 seconds), which works through
oauth-proxy and the OpenShift router without streaming. The page does not change the routing: when it is
down, the router works the same.

The gitops repo deploys it behind the OpenShift oauth-proxy (sign-in with the cluster users). The
ServiceAccount of the page is the OAuth client, so oauth-proxy asks only the scopes `user:info` and
`user:check-access`: OpenShift refuses `user:full` for a ServiceAccount client. That is why the page
checks the user and then writes with its own ServiceAccount.

## API

| Method and path | Meaning |
|---|---|
| `GET /` | The page |
| `GET /api/config` | Texts of the page and the signed-in user |
| `GET /api/state` | Labels, counters and the last 30 decisions |
| `GET /api/events?after=<seq>&timeout=<s>` | What changed after `seq`; waits up to `timeout` seconds (max 25) |
| `POST /api/namespaces/<name>/data-class` | Body `{"value": "restricted" \| "public"}`; needs the oauth-proxy access token |
| `GET /healthz`, `GET /readyz` | Probes |

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_NAMESPACES` | `agentic-triage,payments` | Namespaces shown as cards, in this order; only these can be changed |
| `DATA_CLASS_LABEL` | `sovereign-selfheal.io/data-class` | Label of the namespace policy of the router |
| `ROUTER_NAMESPACE` | `maas-routing` | Namespace of the LiteLLM pods |
| `ROUTER_POD_SELECTOR` | `app=litellm` | Label selector of the LiteLLM pods |
| `ROUTER_CONTAINER` | `litellm` | Container with the router log |
| `SOTA_ALIAS` | `sota-smart` | Model alias of the external model in the router (`routed_to`) |
| `CLUSTER_NAME` | empty | Shown in the header |
| `LOCAL_MODEL_LABEL` / `SOTA_MODEL_LABEL` | `Local model` / `External model` | Names of the two models on the page |
| `TIER_LABELS` | `{}` | JSON object, API-key tier -> name of its agent, for example `{"agents": "triage-agent"}` (column Agent) |
| `NAMESPACE_POLL_SECONDS` / `POD_POLL_SECONDS` | `2` / `10` | Seconds between two reads of the labels / of the router pods |
| `KUBERNETES_ENABLED` | `true` | `false`: no Kubernetes API call (tests, local run of the page) |
| `LOG_LEVEL` | `INFO` | Python log level |

## Develop and test

```bash
uv sync
uv run ruff check .
uv run yamllint .
uv run pytest
KUBERNETES_ENABLED=false uv run uvicorn app.main:app --port 8080   # the page without a cluster
```

After a change of the dependencies: `uv lock`, then
`uv export --frozen --no-dev --no-emit-project --no-header --format requirements-txt > requirements.txt`
(the image installs `requirements.txt` with hashes; CI checks that it matches `uv.lock`).

## Release

Quay builds and publishes the image `quay.io/sovereign-selfheal/routing-live-view:vX.Y.Z` on every git tag
`vX.Y.Z` (build trigger). The CI of this repo only checks the code and that the image builds. The gitops
repo pins the image by digest.

## License

Apache License 2.0, see [`LICENSE`](LICENSE).
