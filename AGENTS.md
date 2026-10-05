# AGENTS.md: `routing-live-view` repository

Guidance for AI coding agents and humans working in this repo. Read it fully before you change anything.

## 1. Purpose

A live web page for the demo: where each LLM request of the agents goes (local GPU or external model),
and the data-class label of the demo namespaces (router v0.11.0, namespace policy). It also builds the
image `quay.io/sovereign-selfheal/routing-live-view`. The `gitops` repo deploys it. This repo contains no
Kubernetes manifests.

## 2. Contracts

| Owner | Items |
|---|---|
| `routing-live-view` (this repo) | The app (`app/`), the page (`app/static/index.html`), tests, `Containerfile`, image tags |
| `router` | The log line `[policy-router] {...}` that the page parses (stable interface, router `AGENTS.md` §2.4), the label key `sovereign-selfheal.io/data-class` and the alias `sota-smart` |
| `gitops` | Deployment, Service, Route, oauth-proxy sidecar, ServiceAccount, Role/RoleBinding (pods, pods/log in the router namespace), the env vars, the image digest |
| `ansible` | The ClusterRoles `sovereign-selfheal-namespace-reader` and `sovereign-selfheal-demo-namespace-labeler` (patch on the demo namespaces only) and their bindings to the ServiceAccount of the page (the gitops AppProject allows no cluster-scoped objects), the namespace labels |

Rules:

1. **Read-only for the routing.** The page never changes how requests are routed, and the router never
   depends on the page. The only write is the namespace label.
2. **The user's RBAC decides a label change.** Write only after a `SelfSubjectAccessReview` with the
   token of the signed-in user says `allowed` (verb `patch` on that namespace). The ServiceAccount may
   patch only the demo namespaces (ClusterRole with `resourceNames`, ansible repo). Keep the allow list:
   only `DEMO_NAMESPACES`, only the values `restricted` and `public`. Log the user of every change.
3. **Metadata only.** The page shows fields of the decision line; it never reads or shows prompt text.
4. **No requests outside the cluster from the page** (no web fonts, no CDN): the demo is about data
   sovereignty.
5. A new field of the decision line is optional for the page: older router versions do not have it.

## 3. Layout

```
app/
  main.py        # FastAPI app: page, /api/*, probes, background tasks
  config.py      # settings from the environment
  kube.py        # small Kubernetes API client (httpx)
  decisions.py   # parser of the [policy-router] log line
  state.py       # counters, recent decisions, long polling
  watchers.py    # namespace labels and router log followers
  static/index.html
tests/           # unit tests, no cluster needed
Containerfile    # ubi9/python-312 + requirements.txt (hashes)
```

## 4. Conventions

- **Python tools with uv** (`uv sync`, `uv run`), never pip on the host. Change a dependency in
  `pyproject.toml`, run `uv lock` and `uv export ... -o requirements.txt`, commit the three files.
- **Tests for every change** (`uv run pytest`); `uv run ruff check .` and `uv run yamllint .` must pass.
- **Pins.** The base image is pinned by digest with a comment that says where and when it was resolved.
- Comments, docs and commit messages in **English**, level B2/C1: short, clear sentences, no idioms.

## 5. Release

1. Merge on `main` with a green CI.
2. Tag `vX.Y.Z` and push the tag: Quay's build trigger publishes
   `quay.io/sovereign-selfheal/routing-live-view:vX.Y.Z`.
3. PR on `gitops`: pin the digest of that tag (`# tag vX.Y.Z, resolved on quay.io on <date>`).

Never move, delete or reuse a tag.

## 6. Out of scope

- Routing decisions and policies → `router` and `gitops` repos.
- Kubernetes objects of the page → `gitops`; cluster-scoped RBAC and namespaces → `ansible`.
