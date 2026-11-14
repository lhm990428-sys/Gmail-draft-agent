import json
import secrets
from types import SimpleNamespace
from uuid import uuid4
from cryptography.fernet import Fernet
from mail_tools.app.config import AppConfig
from mail_tools.app.service import Service


class FakeClient:
    def __init__(self):
        self.created={};self.feedback=[];self.runs=self;self.fail_read=False
    def create_run(self,**kwargs):self.created[str(kwargs["id"])]=kwargs
    def read_project(self,**kwargs):return SimpleNamespace(id="11111111-1111-4111-8111-111111111111")
    async def retrieve(self,identifier,**kwargs):
        if self.fail_read:raise RuntimeError("read unavailable")
        return SimpleNamespace(id=identifier)
    def update_run(self,*args,**kwargs):pass
    def create_feedback(self,rid,key,**kwargs):self.feedback.append(SimpleNamespace(id=kwargs["feedback_id"],run_id=rid,key=key,score=kwargs["score"]))
    def list_feedback(self,**kwargs):return self.feedback


def test_outbox_is_durable_private_and_requires_server_readback(tmp_path):
    client=FakeClient()
    service=Service(AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=True),Fernet.generate_key(),secrets.token_bytes(32),telemetry_client=client)
    try:
        rid=service.start(wait=True)["id"]
        service.store.emit(rid,"context","agent.completed","done","fixed summary",input="PRIVATE RAW MAIL",output="PRIVATE DRAFT",memory={"secret":"PRIVATE RAW MAIL"})
        client.fail_read=True
        assert service.telemetry.flush(limit=100)["failed"]>=1
        assert service.telemetry.coverage(rid)!=1
        from sqlalchemy import update
        from mail_tools.app.store import outbox
        with service.store.engine.begin() as conn:conn.execute(update(outbox).values(next_at=None))
        client.fail_read=False
        assert service.telemetry.flush(limit=100)["failed"]==0
        assert service.telemetry.coverage(rid)==1
        sent=json.dumps(list(client.created.values()),default=str)
        assert "PRIVATE RAW MAIL" not in sent and "PRIVATE DRAFT" not in sent
        ids=set(client.created)
        service.telemetry.flush(limit=100)
        assert set(client.created)==ids
    finally:service.close()


def test_due_event_is_not_starved_by_backoff_rows_before_limit(tmp_path):
    from datetime import datetime,timedelta,timezone
    from sqlalchemy import select,update
    from mail_tools.app.store import outbox
    service=Service(AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=True),Fernet.generate_key(),secrets.token_bytes(32),telemetry_client=FakeClient())
    try:
        rid=service.start(wait=True)["id"]
        with service.store.engine.begin() as conn:
            tail=service.store.history(rid)[-1]["id"]
            last=conn.execute(select(outbox.c.id).where(outbox.c.id!=tail).order_by(outbox.c.id.desc()).limit(1)).scalar()
            conn.execute(update(outbox).values(next_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()))
            conn.execute(update(outbox).where(outbox.c.id==last).values(next_at=None))
        result=service.telemetry.flush(limit=1)
        assert result["delivered"]==1 and result["status"]=="pending"
        assert 0<service.telemetry.coverage(rid)<1
    finally:service.close()


def test_lost_trace_create_response_reconciles_same_remote_id(tmp_path):
    from langsmith.utils import LangSmithConflictError
    from sqlalchemy import update
    from mail_tools.app.store import outbox
    class LostResponse(FakeClient):
        def __init__(self):super().__init__();self.lost=False
        def create_run(self,**kwargs):
            key=str(kwargs['id'])
            if key in self.created:raise LangSmithConflictError('already stored')
            super().create_run(**kwargs)
            if kwargs['name'].startswith('llm.completed') and not self.lost:
                self.lost=True
                raise TimeoutError('synthetic response loss after durable remote write')
    client=LostResponse()
    service=Service(AppConfig(database_dir=tmp_path,llm_mode='scripted',trace_enabled=True),Fernet.generate_key(),secrets.token_bytes(32),telemetry_client=client)
    try:
        rid=service.start(wait=True)['id']
        assert service.telemetry.flush(limit=100)['failed']>=1
        count=len(client.created)
        with service.store.engine.begin() as conn:conn.execute(update(outbox).values(next_at=None))
        service.telemetry.flush(limit=100)
        assert service.telemetry.coverage(rid)==1
        assert len(client.created)==count
    finally:service.close()


def test_audit_stream_keeps_one_open_root_while_acknowledging_new_events(tmp_path):
    client=FakeClient()
    service=Service(AppConfig(database_dir=tmp_path,llm_mode='scripted',trace_enabled=True),Fernet.generate_key(),secrets.token_bytes(32),telemetry_client=client)
    try:
        for _ in range(2):
            service.audit('api.request.completed','done','GET','/api/v1/snapshot')
            assert service.telemetry.flush(limit=100)['status']=='pass'
        roots=[r for r in client.created.values() if r['name']=='system.api.audit.stream']
        assert len(roots)==1 and roots[0]['end_time'] is None
        job=service.store.list('job')[0]
        assert service.telemetry.coverage(job['id'])==1
    finally:service.close()
