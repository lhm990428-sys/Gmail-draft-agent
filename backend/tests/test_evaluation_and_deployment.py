import json
import pytest
from cryptography.fernet import Fernet
from mail_tools.app.service import Service
from mail_tools.app.config import AppConfig
from mail_tools.app.datasets import import_dataset
from mail_tools.app.evaluation import evaluate
from mail_tools.app.deployment import activate,rollback
from mail_tools.app.broker import StaleReview,PolicyDenied


@pytest.fixture
def runtime(tmp_path):
    svc=Service(AppConfig(database_dir=tmp_path/'db',llm_mode='scripted',trace_enabled=False),Fernet.generate_key(),b'approval')
    yield svc
    svc.close()


def test_locked_dataset_and_independent_judge(runtime,tmp_path):
    path=tmp_path/'corpus.json'
    path.write_text(json.dumps({'name':'locked-test','split':'holdout','source':'synthetic','cases':[{'id':'receipt','subject':'수신 확인','body':'자료 수신 여부를 알려주세요.','reference':'REPLY_REQUIRED','requests':'수신 확인'}]}),encoding='utf-8')
    locked=import_dataset(runtime.store,path)
    result=evaluate(runtime,locked['id'])
    experiment=runtime.store.get('experiment',result['id'])
    assert experiment['split']=='holdout' and experiment['count']==1
    judges=[j for j in runtime.store.list('job') if j['id'].startswith('judge-')]
    assert len(judges)==1 and judges[0]['calls']==1 and judges[0]['parent']
    repeated=evaluate(runtime,locked['id'])
    newer=runtime.store.get('experiment',repeated['id'])
    first_case=runtime.store.get('eval-case',experiment['caseIds'][0])
    next_case=runtime.store.get('eval-case',newer['caseIds'][0])
    assert next_case['baselineOutput']==first_case['candidateOutput']
    dataset=runtime.store.get('dataset',locked['id']);dataset['cases'][0]['body']='tampered'
    runtime.store.put('dataset',locked['id'],dataset)
    with pytest.raises(ValueError,match='LOCKED'):evaluate(runtime,locked['id'])


def test_promotion_requires_gates_and_never_expands_deployment_scope(runtime):
    with pytest.raises(StaleReview,match='GATES'):activate(runtime,runtime.release_id)
    with pytest.raises(PolicyDenied):activate(runtime,runtime.release_id,'production')
    with pytest.raises(StaleReview,match='PREVIOUS'):rollback(runtime)
    assert not runtime.store.list('deployment')


def test_approved_local_activation_is_durable_and_rollback_checks_manifest(runtime,monkeypatch):
    import mail_tools.app.deployment as deployment
    release=runtime.store.get('release',runtime.release_id)
    release.update(decision='READY_FOR_APPROVAL',gates=[{'status':'PASS'}]*8)
    monkeypatch.setattr(deployment,'assess',lambda *args:(release,{},{}))
    activate(runtime,runtime.release_id);activate(runtime,runtime.release_id)
    assert rollback(runtime)['state']=='rolled_back'
    assert len(runtime.store.list('deployment-audit'))==3
    manifest=runtime.store.get('manifest',runtime.release_id);manifest['policy']='tampered'
    runtime.store.put('manifest',runtime.release_id,manifest)
    with pytest.raises(StaleReview):rollback(runtime)
