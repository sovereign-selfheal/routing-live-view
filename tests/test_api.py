import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.kube import KubeError
from app.main import app


class FakeKube:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def set_namespace_label(self, name, label, value, user_token):
        self.calls.append((name, label, value, user_token))
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


def test_label_change_uses_the_user_token(client):
    r = post(client, "payments", "public")
    assert r.status_code == 200
    label = "sovereign-selfheal.io/data-class"
    assert app.state.kube.calls == [("payments", label, "public", "tok")]


def test_label_change_needs_a_signed_in_user(client):
    assert post(client, "payments", "public", token=None).status_code == 401


def test_label_change_only_for_demo_namespaces_and_values(client):
    assert post(client, "kube-system", "public").status_code == 404
    assert post(client, "payments", "secret").status_code == 400
    assert app.state.kube.calls == []


def test_label_change_forbidden_for_the_user(client):
    app.state.kube.error = KubeError(403, "forbidden")
    r = post(client, "payments", "restricted")
    assert r.status_code == 403
    assert "cannot change" in r.json()["error"]
