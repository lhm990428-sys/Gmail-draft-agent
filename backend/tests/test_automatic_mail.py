import time
import secrets
from datetime import datetime,timezone
from cryptography.fernet import Fernet
import pytest
from mail_tools.app.config import AppConfig
from mail_tools.app.service import Service
from mail_tools.app.models import ScriptedModel
from mail_tools.app.broker import fixture_mail,StaleReview


class RecordingModel(ScriptedModel):
    def __init__(self,overrides=None):super().__init__(overrides,economy=True);self.roles=[]
    def invoke(self,role,payload):self.roles.append(role);return super().invoke(role,payload)


def make_service(path,model=None):
    return Service(AppConfig(database_dir=path,llm_mode="scripted",trace_enabled=False,economy_profile=True,automatic_mail=True,allow_real_mail_export=True),Fernet.generate_key(),secrets.token_bytes(32),model=model)


def wait(service,rid):
    end=time.monotonic()+5
    while service.store.get("job",rid)["status"]=="running" and time.monotonic()<end:time.sleep(.01)
    return service.store.get("job",rid)


def test_economy_reply_three_calls_and_local_review_only(tmp_path):
    model=RecordingModel();service=make_service(tmp_path,model)
    try:
        mail={**fixture_mail("reply"),"source":"gmail"}
        service.gmail.preflight=lambda *_:pytest.fail("Must not write or request compose")
        rid=service.start(source="gmail",custom_mail=mail,wait=True)["id"]
        assert model.roles==["triage","draft","critic"]
        job=service.store.get("job",rid);assert job["status"]=="review"
        result=service.decide(job["mailId"],1,"approve")
        assert result["status"]=="reviewed" and result["draftId"] is None
        assert not service.store.list("intent")
    finally:service.close()


def test_economy_no_reply_one_call_and_uncertainty_no_draft(tmp_path):
    model=RecordingModel();service=make_service(tmp_path,model)
    try:
        rid=service.start(kind="newsletter",wait=True)["id"]
        assert model.roles==["triage"]
        assert service.store.get("job",rid)["status"]=="success"
        model.roles.clear()
        model.overrides["triage"]={"category":"REVIEW_REQUIRED","confidence":.5,"priority":"normal","reason":"불확실","summary":"질문","requests":[],"risk":"high","injection":False,"evidence":["fixture-message"]}
        rid=service.start(wait=True)["id"]
        assert model.roles==["triage"] and service.harness.state(rid).next==("human_review",)
        assert service.mail(service.store.get("job",rid)["mailId"])["draftBody"]==""
    finally:service.close()


def test_auto_collection_advertising_dedupe_and_pause(tmp_path):
    model=RecordingModel();service=make_service(tmp_path,model)
    try:
        stamp=datetime.now(timezone.utc).isoformat()
        items=[{"messageId":"auto-1","threadId":"thread-a","sender":"tester","address":"tester@example.invalid","subject":"자동 테스트","receivedAt":stamp,"reason":None},{"messageId":"ad-1","threadId":"ad-a","sender":"bulk","address":"bulk@example.invalid","subject":"광고","receivedAt":stamp,"reason":"프로모션+대량발송"}]
        service.gmail.recent_page=lambda *args:(items,None)
        service.gmail.read_message=lambda mid,since:{**fixture_mail("reply"),"source":"gmail","latestMessageId":mid,"threadId":"thread-a"}
        service.mailbox.tick()
        first=next(i for i in service.mailbox.view()["items"] if i["messageId"]=="auto-1")
        assert first["runId"];wait(service,first["runId"])
        service.mailbox.tick();service.mailbox.tick()
        assert len(model.roles)==3 and len([j for j in service.store.list("job") if j.get("mailId")])==1
        assert next(i for i in service.mailbox.view()["items"] if i["messageId"]=="ad-1")["status"]=="excluded"
        service.mailbox.pause(True)
        service.gmail.recent_page=lambda *args:pytest.fail("Paused collector must not fetch")
        service.mailbox.tick()
        assert service.store.get("mailbox-control","main")["paused"]
    finally:service.close()


def test_new_message_invalidates_old_review(tmp_path):
    service=make_service(tmp_path)
    try:
        first={**fixture_mail("reply"),"source":"gmail","threadId":"same","latestMessageId":"message-old"}
        rid=service.start(source="gmail",custom_mail=first,wait=True)["id"]
        mid=service.store.get("job",rid)["mailId"]
        service.start(source="gmail",custom_mail={**first,"latestMessageId":"message-new"},wait=True)
        with pytest.raises(StaleReview,match="SUPERSEDES"):service.decide(mid,1,"approve")
    finally:service.close()


def test_receipt_dedupe_survives_process_restart(tmp_path):
    config=AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=False,economy_profile=True,automatic_mail=True,allow_real_mail_export=True)
    key=Fernet.generate_key();approval=secrets.token_bytes(32)
    model=RecordingModel();service=Service(config,key,approval,model=model)
    mail={**fixture_mail("reply"),"source":"gmail"}
    receipt="gmail-auto-v1:restart-id"
    rid=service.start(source="gmail",custom_mail=mail,receipt=receipt,wait=True)["id"]
    service.mailbox.pause(True);service.close()
    model=RecordingModel();service=Service(config,key,approval,model=model)
    try:
        assert service.mailbox.view()["paused"]
        assert service.start(source="gmail",custom_mail=mail,receipt=receipt,wait=True)["id"]==rid
        assert model.roles==[]
    finally:service.close()


def test_recent_collector_keeps_page_cursor_and_does_not_fetch_large_body(tmp_path):
    service=make_service(tmp_path)
    try:
        stamp=datetime.now(timezone.utc).isoformat();tokens=[]
        def page(since,until,token):
            tokens.append(token)
            return ([{"messageId":"long-1","threadId":"long-thread","sender":"tester","address":"t@example.invalid","subject":"길이 초과","receivedAt":stamp,"reason":None}],"second-page" if token is None else None)
        service.gmail.recent_page=page
        service.gmail.read_message=lambda *args:{**fixture_mail("reply"),"source":"gmail","contentLimited":True}
        service.mailbox.tick();service.mailbox.tick()
        assert tokens==[None,"second-page",None]
        assert not [j for j in service.store.list("job") if j.get("mailId")]
        assert service.mailbox.view()["items"][0]["status"]=="needs_review"
    finally:service.close()


def test_gmail_scope_uses_metadata_and_72h_boundary(tmp_path,monkeypatch):
    from mail_tools.app.broker import GmailBroker
    stamp=time.time();calls=[]
    class Request:
        def __init__(self,value):self.value=value
        def execute(self,**kwargs):return self.value
    class API:
        def users(self):return self
        def messages(self):return self
        def list(self,**kwargs):
            calls.append(kwargs)
            return Request({"messages":[{"id":"self"},{"id":"old"},{"id":"ad"}]})
        def get(self,**kwargs):
            calls.append(kwargs);mid=kwargs['id']
            return Request({"id":mid,"threadId":mid,"internalDate":str(int((stamp-73*3600 if mid=='old' else stamp)*1000)),"labelIds":["INBOX","SENT"] if mid=='self' else ["INBOX","CATEGORY_PROMOTIONS"],"payload":{"headers":[{"name":"From","value":"tester@example.invalid"},{"name":"Subject","value":"test"}]+([{"name":"List-Unsubscribe","value":"<https://example.invalid>"}] if mid=='ad' else [])}})
        def close(self):pass
    broker=GmailBroker(AppConfig(database_dir=tmp_path,allow_real_mail_export=True),b'key')
    monkeypatch.setattr(broker,'_service',lambda:API())
    items,_=broker.recent_page(stamp-72*3600,stamp+1)
    assert {i['messageId'] for i in items}=={'self','ad'}
    assert next(i for i in items if i['messageId']=='ad')['reason']
    assert calls[0]['labelIds']==['INBOX'] and 'after:' in calls[0]['q'] and 'before:' in calls[0]['q']
    assert all(c['format']=='metadata' for c in calls if 'id' in c)
