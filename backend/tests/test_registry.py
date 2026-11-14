import secrets
from cryptography.fernet import Fernet
from pydantic import BaseModel
import pytest
from mail_tools.app.config import AppConfig
from mail_tools.app.registry import AgentRegistry,AgentSpec
from mail_tools.app.models import ScriptedModel
from mail_tools.app.service import Service


class Knowledge(BaseModel): facts:list[str]


def test_new_worker_uses_same_graph_event_and_manifest_contract(tmp_path):
    extension=AgentSpec("knowledge",Knowledge,"Return only supplied facts.")
    registry=AgentRegistry("scripted",[extension])
    model=ScriptedModel({"supervisor":{"agents":["context","triage","risk","draft","critic","knowledge"],"reason":"registered extension"},"knowledge":{"facts":["synthetic known fact"]}})
    service=Service(AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=False),Fernet.generate_key(),secrets.token_bytes(32),model=model,agent_registry=registry)
    try:
        rid=service.start(wait=True)["id"]
        assert service.store.get("job",rid)["status"]=="review"
        assert service.harness.state(rid).values["results"]["knowledge"]["facts"]
        tape=service.runtime(rid)
        assert any(n["id"]=="knowledge" for n in tape["nodes"])
        assert any(e["source"]=="supervisor" and e["target"]=="knowledge" for e in tape["edges"])
        assert any(a["id"]=="knowledge" for a in service.manifest["agents"])
    finally:service.close()


def test_registry_blocks_cycles_rights_and_unregistered_children():
    with pytest.raises(ValueError,match="RIGHTS"):AgentRegistry("x",[AgentSpec("knowledge",Knowledge,"x",allowed_tools=("gmail.send",))])
    with pytest.raises(ValueError,match="UNREGISTERED"):AgentRegistry("x",[AgentSpec("knowledge",Knowledge,"x",children=("missing",))])
    with pytest.raises(ValueError,match="CYCLE"):AgentRegistry("x",[AgentSpec("knowledge",Knowledge,"x",children=("knowledge",))])
