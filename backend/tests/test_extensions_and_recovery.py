import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from cryptography.fernet import Fernet
from langgraph.graph import StateGraph,START,END
from mail_tools.app.config import AppConfig
from mail_tools.app.service import Service,Busy
from mail_tools.app.registry import AgentRegistry,AgentSpec
from mail_tools.app.harness import State,WorkerOutput
from mail_tools.app.models import ScriptedModel
from test_registry import Knowledge


def knowledge_team(harness):
    graph=StateGraph(State,output_schema=WorkerOutput)
    def delegate(state):
        harness.store.emit(state['run_id'],'knowledge_team','task.dispatched','running','Registered team supervisor')
        result=harness.call('researcher',state)
        return {'results':{'researcher':result,'knowledge_team':result}}
    graph.add_node('delegation',delegate)
    graph.add_edge(START,'delegation');graph.add_edge('delegation',END)
    return graph.compile()


def test_nested_team_supervisor_shares_checkpoint_budget_and_events(tmp_path):
    registry=AgentRegistry('scripted',[
        AgentSpec('researcher',Knowledge,'Only supplied facts.'),
        AgentSpec('knowledge_team',Knowledge,'Supervise research.',kind='team',children=('researcher',),factory=knowledge_team)])
    model=ScriptedModel({'supervisor':{'agents':list(registry.worker_ids),'reason':'registered team'},'researcher':{'facts':['known fixture fact']}})
    service=Service(AppConfig(database_dir=tmp_path,llm_mode='scripted',trace_enabled=False),Fernet.generate_key(),b'approval',model=model,agent_registry=registry)
    try:
        rid=service.start(wait=True)['id']
        assert service.store.get('job',rid)['status']=='review'
        assert service.harness.state(rid).values['results']['researcher']['facts']
        assert any(e['source']=='knowledge_team' and e['target']=='researcher' for e in service.runtime(rid)['edges'])
        assert service.manifest['agent_contracts'][-1]['factory_hash']
    finally:service.close()


def test_gateway_receipt_survives_missing_receipt_document(tmp_path):
    service=Service(AppConfig(database_dir=tmp_path,llm_mode='scripted',trace_enabled=False),Fernet.generate_key(),b'approval')
    try:
        first=service.start(wait=True,receipt='same-trusted-command')['id']
        second=service.start(wait=True,receipt='same-trusted-command')['id']
        assert first==second
        assert len(service.store.list('mail'))==1
    finally:service.close()


def test_reconcile_cannot_race_inflight_write(tmp_path):
    service=Service(AppConfig(database_dir=tmp_path,llm_mode='scripted',trace_enabled=False),Fernet.generate_key(),b'approval')
    entered,release=threading.Event(),threading.Event()
    try:
        rid=service.start(wait=True)['id'];mail=service.mail(service.store.get('job',rid)['mailId'])
        original=service.fixture.create_draft
        def delayed(*args):
            entered.set();assert release.wait(5)
            return original(*args)
        service.fixture.create_draft=delayed
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(service.decide,mail['id'],1,'approve')
            assert entered.wait(5)
            try:
                with pytest.raises(Busy):service.reconcile(mail['id'])
                assert service.snapshot()['runs']
            finally:release.set()
            assert future.result()['status']=='draft_saved'
        assert len(service.store.list('local-draft'))==1
    finally:release.set();service.close()
