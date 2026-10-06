import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.kube import KubeError
from app.main import app


class FakeKube:
    def __init__(self, error=None, allowed=True):
        self.calls = []
        self.reviews = []
        self.error = error
        self.allowed = allowed

    async def user_can_patch_namespace(self, name, user_token):
        self.reviews.append((name, user_token))
        return self.allowed

    async def set_namespace_label(self, name, label, value):
        self.calls.append((name, label, value))
        if self.error:
            raise self.error

    async def close(self):
        pass


@pytest.fixture
def client():
    app.state.settings = Settings(kubernetes_enabled=False, cluster_name="ocp.test",
                                  sota_model_label="gemini-2.5-pro")
    app.state.kube = FakeKube()
    with TestClient(app) as c:
        yield c
    del app.state.kube


def post(client, name, value, token="tok"):
    headers = {"X-Forwarded-Access-Token": token, "X-Forwarded-User": "amedeos"} if token else {}
    return client.post(f"/api/namespaces/{name}/data-class", json={"value": value}, headers=headers)


def test_index_and_config(client):
    assert "Routing Live View" in client.get("/").text
    cfg = client.get("/api/config", headers={"X-Forwarded-User": "amedeos"}).json()
    assert cfg["demo_namespaces"] == ["agentic-triage", "payments"]
    assert cfg["label"] == "sovereign-selfheal.io/data-class"
    assert cfg["user"] == "amedeos" and cfg["cluster_name"] == "ocp.test"


def test_state_and_events(client):
    app.state.live.add_decision({"destination": "local", "ns_restricted": ["payments"],
                                 "namespaces": ["payments"]})
    assert client.get("/api/state").json()["counters"]["restricted"] == 1
    out = client.get("/api/events?after=0&timeout=0").json()
    assert [e["seq"] for e in out["events"]] == [1]


def test_label_change_checks_the_user_then_patches(client):
    r = post(client, "payments", "public")
    assert r.status_code == 200
    assert app.state.kube.reviews == [("payments", "tok")]
    label = "sovereign-selfheal.io/data-class"
    assert app.state.kube.calls == [("payments", label, "public")]


def test_label_change_needs_a_signed_in_user(client):
    assert post(client, "payments", "public", token=None).status_code == 401


def test_label_change_only_for_demo_namespaces_and_values(client):
    assert post(client, "kube-system", "public").status_code == 404
    assert post(client, "payments", "secret").status_code == 400
    assert app.state.kube.calls == []


def test_label_change_forbidden_for_the_user(client):
    app.state.kube.allowed = False
    r = post(client, "payments", "restricted")
    assert r.status_code == 403
    assert "cannot change" in r.json()["error"]
    assert app.state.kube.calls == []  # nothing written


def test_label_change_error_of_the_page(client):
    app.state.kube.error = KubeError(403, "forbidden")
    r = post(client, "payments", "restricted")
    assert r.status_code == 502
    assert "page cannot change" in r.json()["error"]


async def test_kube_access_review_and_patch(tmp_path):
    import httpx

    from app.kube import Kube

    (tmp_path / "token").write_text("sa-token")
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.headers["Authorization"],
                     request.read()))
        if request.url.path.endswith("selfsubjectaccessreviews"):
            return httpx.Response(201, json={"status": {"allowed": True}})
        return httpx.Response(200, json={})

    kube = Kube(base="https://api.test", sa_dir=str(tmp_path),
                transport=httpx.MockTransport(handler))
    assert await kube.user_can_patch_namespace("payments", "user-token") is True
    await kube.set_namespace_label("payments", "k", "public")
    await kube.close()
    assert seen[0][:3] == ("POST", "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                           "Bearer user-token")
    assert b'"name":"payments"' in seen[0][3] and b'"verb":"patch"' in seen[0][3]
    assert seen[1][:3] == ("PATCH", "/api/v1/namespaces/payments", "Bearer sa-token")
