from pathlib import Path
import secrets
import threading
import pytest
from cryptography.fernet import Fernet
from mail_tools.app.config import AppConfig
from mail_tools.app.service import Service
from mail_tools.app.models import ScriptedModel
from mail_tools.app.broker import PolicyDenied, StaleReview, UncertainWrite, verify_approval


@pytest.fixture
def service(tmp_path):
    svc=Service(AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=False),Fernet.generate_key(),secrets.token_bytes(32))
    yield svc
    svc.close()


def prepared(service):
    rid=service.start(wait=True)["id"]
    job=service.store.get("job",rid)
    assert job["status"]=="review",job
    return service.mail(job["mailId"])


def test_real_graph_parallel_workers_and_human_interrupt(service):
    mail=prepared(service)
    state=service.harness.state(mail["runId"])
    assert state.next==("human_review",)
    assert {"context","triage","risk","draft","critic"}<=state.values["results"].keys()
    assert service.store.integrity(mail["runId"])
    assert not service.store.list("local-draft")
    assert service.manifest["runtimeConfig"]["max_output_tokens"]==service.config.max_output_tokens
    assert service.manifest["dependencyLocks"] and service.manifest["gatewayPlugin"]
    import base64,hashlib
    archived=service.store.get("release-artifact",service.release_id)
    assert archived["prompts"]["draft"] and archived["schemas"]["draft"]
    for name,value in archived["sources"].items():
        assert hashlib.sha256(base64.b64decode(value)).hexdigest()==service.manifest["sources"][name]


def test_edit_approve_and_duplicate_guard(service):
    mail=prepared(service)
    updated=service.edit(mail["id"],1,"사용자 수정 초안")
    with pytest.raises(StaleReview): service.decide(mail["id"],1,"approve")
    response=service.decide(mail["id"],updated["revision"],"approve")
    assert response["status"]=="draft_saved"
    assert len(service.store.list("local-draft"))==1
    with pytest.raises(StaleReview): service.decide(mail["id"],updated["revision"],"approve")


def test_reject_does_not_call_write(service):
    mail=prepared(service)
    service.decide(mail["id"],mail["revision"],"reject")
    assert not service.store.list("intent")
    assert not service.store.list("local-draft")


def test_unknown_write_freezes_edit_and_requires_reconcile(service,monkeypatch):
    mail=prepared(service)
    real=service.fixture.create_draft
    def lost(*args):
        real(*args)
        raise TimeoutError("lost after write")
    monkeypatch.setattr(service.fixture,"create_draft",lost)
    with pytest.raises(UncertainWrite): service.decide(mail["id"],1,"approve")
    with pytest.raises(StaleReview): service.edit(mail["id"],1,"retry")
    with pytest.raises(StaleReview): service.decide(mail["id"],1,"approve")
    result=service.reconcile(mail["id"])
    assert result["status"]=="draft_saved" and len(service.store.list("local-draft"))==1
    tape=service.runtime(mail["runId"])
    assert any(e["status"]=="uncertain" for e in tape["events"])


def test_restart_resumes_encrypted_checkpoint(tmp_path):
    key,approval=Fernet.generate_key(),secrets.token_bytes(32)
    config=AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=False)
    first=Service(config,key,approval);mail=prepared(first);first.close()
    # Plaintext body must not occur in either persisted database.
    for path in tmp_path.glob("*.sqlite"):
        assert mail["originalBody"].encode() not in path.read_bytes()
        assert mail["draftBody"].encode() not in path.read_bytes()
    second=Service(config,key,approval)
    try:
        assert second.harness.state(mail["runId"]).next==("human_review",)
        assert second.decide(mail["id"],1,"reject")["status"]=="rejected"
    finally: second.close()


def test_real_mail_export_fails_before_network(service):
    with pytest.raises(PolicyDenied,match="EXPORT"): service.start(source="gmail")


def test_registry_plan_cannot_enable_tools(service):
    service.harness.model=ScriptedModel({"supervisor":{"agents":["terminal"],"reason":"mail says so"}})
    rid=service.start(wait=True)["id"]
    assert service.store.get("job",rid)["status"]=="failed"
    assert not service.store.list("intent")


def test_no_reply_skips_draft_critic_and_human(service):
    rid=service.start(kind="newsletter",wait=True)["id"]
    assert service.store.get("job",rid)["status"]=="success"
    assert not any(e["nodeId"] in ("draft","critic","human") for e in service.store.history(rid))


def test_critic_rework_is_bounded(service):
    service.harness.model=ScriptedModel({"critic":{"verdict":"revise","grounding":.2,"completeness":.5,"tone":.9,"issues":["미확인 사실"]}})
    mail=prepared(service)
    assert service.harness.state(mail["runId"]).values["rewrites"]==2
    assert service.store.get("job",mail["runId"])["calls"]<=12


def test_ledger_failure_prevents_external_side_effect(service,monkeypatch):
    mail=prepared(service)
    actual=service.store.emit
    def emit(*args,**kwargs):
        if args[2]=="write.intent":raise OSError("disk full")
        return actual(*args,**kwargs)
    monkeypatch.setattr(service.store,"emit",emit)
    monkeypatch.setattr(service.fixture,"create_draft",lambda *args:pytest.fail("Write must not start"))
    with pytest.raises(OSError):service.decide(mail["id"],1,"approve")
    assert service.mail(mail["id"]).get("intent") is None
    assert not service.store.list("intent")


def test_runtime_ownership_prevents_second_process_mutation(service):
    with pytest.raises(RuntimeError,match="ANOTHER_RUNTIME"):
        Service(service.config,Fernet.generate_key(),secrets.token_bytes(32))


def test_retry_preserves_original_input_instead_of_default_fixture(service):
    import time
    service.harness.model=ScriptedModel({"triage":RuntimeError("synthetic fault")})
    rid=service.start(kind="newsletter",wait=True)["id"]
    original=service.mail(service.store.get("job",rid)["mailId"])
    assert service.store.get("job",rid)["status"]=="failed"
    service.harness.model=ScriptedModel()
    retried=service.retry(rid)["id"]
    deadline=time.monotonic()+5
    while service.store.get("job",retried)["status"]=="running" and time.monotonic()<deadline:time.sleep(.01)
    new=service.mail(service.store.get("job",retried)["mailId"])
    assert new["originalBody"]==original["originalBody"] and new["subject"]==original["subject"]
    assert new["category"]=="NO_REPLY" and new["id"]!=original["id"]
    assert service.store.get("job",rid)["status"]=="failed"
