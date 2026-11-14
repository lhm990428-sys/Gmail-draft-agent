import secrets
import time
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest
from mail_tools.app.config import AppConfig
from mail_tools.app.service import Service
from mail_tools.app.server import create_app


@pytest.fixture
def setup(tmp_path):
    service=Service(AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=False),Fernet.generate_key(),secrets.token_bytes(32))
    token=secrets.token_urlsafe(40)
    client=TestClient(create_app(service,token,run_telemetry=False),base_url="http://127.0.0.1:8000")
    yield service,client,token
    client.close();service.close()


def login(client,token):
    response=client.post("/api/v1/session/bootstrap",json={"token":token},headers={"Origin":"http://127.0.0.1:8000"})
    assert response.status_code==200,response.text
    return {"Origin":"http://127.0.0.1:8000","X-CSRF-Token":response.json()["csrf"]}


def test_auth_origin_csrf_and_single_use_bootstrap(setup):
    service,client,token=setup
    assert client.get("/api/v1/snapshot").status_code==401
    assert client.post("/api/v1/session/bootstrap",json={"token":token},headers={"Origin":"https://attacker.invalid"}).status_code==403
    headers=login(client,token)
    assert client.post("/api/v1/session/bootstrap",json={"token":token},headers=headers).status_code==403
    assert client.post("/api/v1/runs",json={}).status_code==403
    assert client.post("/api/v1/runs",json={},headers={"Origin":"http://127.0.0.1:8000"}).status_code==403
    assert client.get("/api/v1/snapshot").status_code==200
    assert "HttpOnly" in client.cookies.get("hermes_session","") or client.cookies.get("hermes_session")


def test_http_workflow_persistence_and_gate_rejection(setup):
    service,client,token=setup;headers=login(client,token)
    response=client.post("/api/v1/runs",json={"query":"label:agent-test","maxItems":10},headers=headers)
    assert response.status_code==201,response.text
    rid=response.json()["id"]
    deadline=time.monotonic()+10
    while service.store.get("job",rid)["status"]=="running" and time.monotonic()<deadline: time.sleep(.01)
    snapshot=client.get("/api/v1/snapshot").json()
    assert snapshot["runs"][0]["status"]=="review"
    mail=snapshot["mails"][0]
    tape=client.get(f"/api/v1/runs/{rid}/runtime").json()
    assert tape["source"]=="fixture" and any(e["nodeId"]=="human" for e in tape["events"])
    assert client.get(f"/api/v1/runs/{rid}/runtime?mode=rework").status_code==403
    assert client.post(f"/api/v1/releases/{service.release_id}/promote",json={"target":"canary"},headers=headers).status_code==409
    response=client.post(f"/api/v1/reviews/{mail['id']}/decision",json={"revision":1,"action":"approve"},headers=headers)
    assert response.status_code==200,response.text
    assert response.json()["draftId"].startswith("local-draft-")
    assert client.post("/api/v1/mock/scenario",json={"id":"ready-release"},headers=headers).status_code==405


def test_api_does_not_accept_arbitrary_queries_or_mail_export(setup):
    _,client,token=setup;headers=login(client,token)
    assert client.post("/api/v1/runs",json={"query":"in:anywhere"},headers=headers).status_code==403
    assert client.post("/api/v1/runs",json={"source":"gmail"},headers=headers).status_code==403
    assert client.get("/api/v1/snapshot",headers={"Host":"attacker.invalid"}).status_code==400
