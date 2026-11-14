from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
from cryptography.fernet import Fernet
import pytest
from langsmith.utils import LangSmithConflictError
from mail_tools.app.config import AppConfig
from mail_tools.app.store import Store
from mail_tools.app.telemetry import Telemetry


def test_duplicate_span_end_requires_readback_and_preserves_parent(tmp_path):
    store=Store(tmp_path,Fernet.generate_key());telemetry=Telemetry(store,AppConfig(database_dir=tmp_path))
    current=datetime.now(timezone.utc);requested=current+timedelta(seconds=3)
    identifier,parent,project=str(uuid4()),str(uuid4()),str(uuid4())
    state={'end':current};captured=[]
    async def read(*args):return SimpleNamespace(trace_id=parent,dotted_order='fixed-parent.fixed-child',start_time=current,end_time=state['end'])
    telemetry._retrieve=read
    class Client:
        def update_run(self,*args,**kwargs):
            captured.append(kwargs)
            raise LangSmithConflictError('Duplicate update')
    try:
        with pytest.raises(RuntimeError,match='READBACK'):telemetry.end_span(Client(),identifier,project,requested,parent)
        assert store.get('trace-ended',identifier) is None
        assert str(captured[0]['parent_run_id'])==parent
        state['end']=requested
        telemetry.end_span(Client(),identifier,project,requested,parent)
        assert store.get('trace-ended',identifier)['at']==requested.isoformat()
    finally:store.close()
