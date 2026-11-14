import asyncio
from datetime import datetime, timezone, timedelta
import os
import threading
import time
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import select, update,or_,func
from mail_tools.settings import load_settings
from mail_tools.secrets import get_secret
from .store import outbox, now


class Telemetry:
    def __init__(self,store,config,client=None):
        self.store,self.config,self.injected = store,config,client
        self.lock=threading.Lock()
        self.reader=None
        self.projection_version=2
        if config.trace_enabled and not store.get("trace-projection","v2"):
            with store.lock,store.engine.begin() as connection:
                connection.execute(update(outbox).values(status="pending",attempts=0,next_at=None))
                store.put("trace-projection","v2",{"version":2,"at":now()},connection)
    def client(self):
        if self.injected: return self.injected
        if os.getenv("LANGSMITH_RUNS_ENDPOINTS") or os.getenv("LANGCHAIN_RUNS_ENDPOINTS"): raise RuntimeError("TRACE_REPLICATION_NOT_APPROVED")
        from langsmith import Client
        settings=load_settings();key=get_secret("langsmith-api-key")
        if not key: raise RuntimeError("LANGSMITH_CREDENTIAL_MISSING")
        return Client(api_url=settings.langsmith_endpoint,api_key=key,workspace_id=settings.langsmith_workspace_id or None,
            hide_inputs=True,hide_outputs=lambda values:{"usage_metadata":values["usage_metadata"]} if "usage_metadata" in values else {},
            auto_batch_tracing=False,tracing_mode="langsmith",otel_enabled=False,omit_traced_runtime_info=True,timeout_ms=5000)

    def flush(self,limit=50):
        with self.lock:return self._flush(limit)

    async def _retrieve(self,client,identifier,project_id):
        if self.injected:return await client.runs.retrieve(identifier,project_id=project_id)
        # Public generated synchronous client owns both v2 resources and transport.
        # The pinned handwritten AsyncClient does not close its generated transport.
        from langsmith import Langsmith
        settings=load_settings()
        if self.reader is not None:return self._read_v2(self.reader,identifier,project_id)
        with Langsmith(base_url=settings.langsmith_endpoint,api_key=get_secret("langsmith-api-key"),tenant_id=settings.langsmith_workspace_id or None,timeout=5,max_retries=0) as reader:
            return self._read_v2(reader,identifier,project_id)

    @staticmethod
    def _read_v2(reader,identifier,project_id):
        for attempt in range(2):
            try:return reader.runs.retrieve(identifier,project_id=project_id,selects=["ID","TRACE_ID","DOTTED_ORDER","START_TIME","END_TIME"])
            except Exception as error:
                if getattr(error,"status_code",None)!=404 or attempt==1:raise
                time.sleep(.3)

    def end_span(self,client,identifier,project_id,end_time,parent_id=None):
        if self.injected:
            client.update_run(UUID(identifier),end_time=end_time,outputs={});return
        ended=self.store.get("trace-ended",identifier)
        if ended and datetime.fromisoformat(ended["at"])>=end_time:return
        current=asyncio.run(self._retrieve(client,identifier,str(project_id)))
        if current.end_time and current.end_time>=end_time:
            self.store.put("trace-ended",identifier,{"at":current.end_time.isoformat()});return
        address=self.store.get("trace-address",identifier)
        if address is None:
            run=current
            if not run.trace_id or not run.dotted_order or not run.start_time:raise RuntimeError("TRACE_PARTITION_ADDRESS_MISSING")
            address={"trace_id":str(run.trace_id),"dotted_order":run.dotted_order,"start_time":run.start_time.isoformat()}
            self.store.put("trace-address",identifier,address)
        try:
            client.update_run(UUID(identifier),parent_run_id=UUID(parent_id) if parent_id else None,session_id=project_id,trace_id=UUID(address["trace_id"]),dotted_order=address["dotted_order"],start_time=datetime.fromisoformat(address["start_time"]),end_time=end_time,outputs={})
        except Exception as error:
            from langsmith.utils import LangSmithConflictError
            if not isinstance(error,LangSmithConflictError):raise
        read=asyncio.run(self._retrieve(client,identifier,str(project_id)))
        if not read.end_time or read.end_time<end_time:raise RuntimeError("SPAN_END_READBACK_PENDING")
        self.store.put("trace-ended",identifier,{"at":read.end_time.isoformat()})

    def create_span(self,client,project,**kwargs):
        try:client.create_run(**kwargs)
        except Exception as error:
            from langsmith.utils import LangSmithConflictError
            if not isinstance(error,LangSmithConflictError):raise
            info=client.read_project(project_name=project)
            existing=asyncio.run(self._retrieve(client,str(kwargs["id"]),str(info.id)))
            if str(existing.id)!=str(kwargs["id"]):raise RuntimeError("TRACE_MAPPING_MISMATCH")
            if not self.injected and (str(existing.trace_id)!=str(kwargs["trace_id"]) or existing.dotted_order!=kwargs["dotted_order"]):raise RuntimeError("TRACE_MAPPING_MISMATCH")

    def _flush(self,limit=50):
        if not self.config.trace_enabled:return {"status":"disabled","delivered":0}
        if self.injected:return self._deliver(limit)
        from langsmith import Langsmith
        settings=load_settings()
        with Langsmith(base_url=settings.langsmith_endpoint,api_key=get_secret("langsmith-api-key"),tenant_id=settings.langsmith_workspace_id or None,timeout=5,max_retries=0) as reader:
            self.reader=reader
            try:return self._deliver(limit)
            finally:self.reader=None

    def _deliver(self,limit=50):
        if not self.config.trace_enabled: return {"status":"disabled","delivered":0}
        client=self.client(); settings=load_settings()
        project=settings.langsmith_project.replace("-setup","-runtime")+"-v2"
        delivered,failed=0,0
        project_info=None
        with self.store.engine.connect() as conn:
            pending=conn.execute(select(outbox).where(outbox.c.status!="confirmed",or_(outbox.c.next_at.is_(None),outbox.c.next_at<=now())).order_by(outbox.c.attempts,outbox.c.id).limit(limit)).mappings().all()
        for row in pending:
            if row["next_at"] and row["next_at"]>now(): continue
            value=self.store.open(row["payload"]); rid=value["runId"]
            job=self.store.get("job",rid)
            if not job: continue
            mode=(self.store.get("manifest",job["releaseId"]) or {}).get("llmMode",self.config.llm_mode)
            remote_id=str(uuid5(NAMESPACE_URL,"hermes-mail:projection:2:event:"+row["id"]))
            root=str(uuid5(NAMESPACE_URL,"hermes-mail:projection:2:"+rid))
            root_order=datetime.fromisoformat(job["startedAt"]).strftime("%Y%m%dT%H%M%S%fZ")+root
            history=self.store.history(rid)
            final_events=[e for e in history if e["type"] in ("run.completed","run.failed","run.incomplete","diagnosis.created","diagnosis.failed")]
            root_end=datetime.fromisoformat(final_events[-1]["time"] if final_events else history[-1]["time"]) if final_events or job["status"] in ("success","failed") else None
            if job.get("purpose")=="system":
                # A day's audit stream is intentionally open while new requests arrive.
                root_end=None if job["startedAt"][:10]==now()[:10] else datetime.fromisoformat(job["startedAt"][:10]+"T23:59:59.999999+00:00")
            try:
                root_marker=self.store.get("trace-root","v2:"+rid)
                if root_marker is None:
                    self.create_span(client,project,id=UUID(root),name="system.api.audit.stream" if job.get("purpose")=="system" else "supervised.mail.workflow",run_type="chain",inputs={},outputs={},
                        start_time=datetime.fromisoformat(job["startedAt"]),end_time=root_end,project_name=project,trace_id=UUID(root),dotted_order=root_order,
                        extra={"metadata":{"execution_id":rid,"release_id":job["releaseId"],"source":job["source"],"purpose":job.get("purpose","workload"),"model_mode":mode,"projection_version":2}})
                    self.store.put("trace-root","v2:"+rid,{"id":root})
                usage=value.get("usage") or {}
                start=datetime.fromisoformat(value["at"])-timedelta(milliseconds=usage.get("duration_ms",0))
                parent=root
                if value["node"] not in ("gateway","broker","checkpoint","human"):
                    parent=str(uuid5(NAMESPACE_URL,"hermes-mail:projection:2:"+rid+":agent:"+value["node"]))
                    if self.store.get("trace-agent",parent) is None:
                        agent_end=max(e["time"] for e in history if e["nodeId"]==value["node"]) if final_events or job["status"]!="running" else None
                        self.create_span(client,project,id=UUID(parent),name="agent:"+value["node"],run_type="chain",inputs={},outputs={},parent_run_id=UUID(root),trace_id=UUID(root),dotted_order=root_order+"."+datetime.fromisoformat(job["startedAt"]).strftime("%Y%m%dT%H%M%S%fZ")+parent,start_time=datetime.fromisoformat(job["startedAt"]),end_time=datetime.fromisoformat(agent_end) if agent_end else None,project_name=project,extra={"metadata":{"execution_id":rid,"agent_id":value["node"],"release_id":job["releaseId"],"projection_version":2}})
                        self.store.put("trace-agent",parent,{"id":parent})
                outputs={}
                if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
                    outputs={"usage_metadata":{"input_tokens":usage["input_tokens"],"output_tokens":usage["output_tokens"],"total_tokens":usage["input_tokens"]+usage["output_tokens"]}}
                if self.store.get("trace-written",remote_id) is None:
                    order=root_order+("."+datetime.fromisoformat(job["startedAt"]).strftime("%Y%m%dT%H%M%S%fZ")+parent if parent!=root else "")+"."+start.strftime("%Y%m%dT%H%M%S%fZ")+remote_id
                    self.create_span(client,project,id=UUID(remote_id),name=value["type"]+":"+value["node"],
                    run_type="llm" if value["type"]=="llm.completed" else "chain",inputs={},outputs=outputs,
                    parent_run_id=UUID(parent),trace_id=UUID(root),dotted_order=order,start_time=start,end_time=datetime.fromisoformat(value["at"]),project_name=project,
                        extra={"metadata":{"execution_id":rid,"release_id":job["releaseId"],"event_id":row["id"],"event_sequence":value["sequence"],"agent_id":value["node"],"status":value["status"],"source":job["source"],"ls_provider":"openai" if mode=="openai" else "scripted","ls_model_name":usage.get("model",self.config.model),"projection_version":2}})
                    self.store.put("trace-written",remote_id,{"acceptedAt":now(),"localEventId":row["id"]})
                    if not self.injected:
                        # Separate durable submission from eventually-consistent readback.
                        with self.store.engine.begin() as conn:
                            conn.execute(update(outbox).where(outbox.c.id==row["id"]).values(status="pending",attempts=row["attempts"]+1,next_at=(datetime.now(timezone.utc)+timedelta(seconds=3)).isoformat()))
                        continue
                # Confirmation requires server readback, not just SDK enqueue success.
                if project_info is None:project_info=client.read_project(project_name=project)
                read=asyncio.run(self._retrieve(client,remote_id,str(project_info.id)))
                if str(read.id)!=remote_id: raise RuntimeError("TRACE_MAPPING_MISMATCH")
                evaluation=value.get("evaluation")
                if evaluation:
                    expected=[]
                    prior={str(item.id):item for item in client.list_feedback(run_ids=[UUID(remote_id)],limit=100)}
                    for rubric in evaluation["rubric"]:
                        fid=uuid5(NAMESPACE_URL,remote_id+":"+rubric["criterion"])
                        if str(fid) in prior:
                            if prior[str(fid)].score!=rubric["score"]:raise RuntimeError("EVALUATION_FEEDBACK_SCORE_MISMATCH")
                        else:client.create_feedback(UUID(remote_id),rubric["criterion"],score=rubric["score"],feedback_id=fid,
                            session_id=project_info.id,start_time=datetime.fromisoformat(value["at"]),extend_trace_retention=False,
                            comment="Versioned synthetic dev regression score; not production holdout.",source_info={"evaluator_version":evaluation["evaluatorVersion"],"dataset_version":evaluation["datasetVersion"],"local_experiment_id":evaluation["experimentId"]})
                        expected.append(str(fid))
                    feedback=list(client.list_feedback(run_ids=[UUID(remote_id)],limit=100))
                    if not set(expected)<={str(item.id) for item in feedback}: raise RuntimeError("EVALUATION_FEEDBACK_READBACK_UNCONFIRMED")
                history=self.store.history(rid)
                # Only the ledger tail seals this segment. Every earlier event is
                # acknowledged independently; an open tail cannot yield 100% coverage.
                if value["sequence"]==history[-1]["sequence"]:
                    if job["status"]=="running" and not final_events:raise RuntimeError("RUN_STILL_ACTIVE")
                    closure_pending=False
                    roles={e["nodeId"] for e in history}-{ "gateway","broker","checkpoint","human" }
                    for role in sorted(roles):
                        agent_id=str(uuid5(NAMESPACE_URL,"hermes-mail:projection:2:"+rid+":agent:"+role))
                        if not self.store.get("trace-agent",agent_id):
                            closure_pending=True;continue
                        last=max(e["time"] for e in history if e["nodeId"]==role)
                        try:self.end_span(client,agent_id,project_info.id,datetime.fromisoformat(last),root)
                        except Exception as error:
                            if isinstance(error,RuntimeError) and str(error)=="SPAN_END_READBACK_PENDING" or getattr(error,"status_code",None)==404:closure_pending=True
                            else:raise
                    try:
                        if root_end is not None:self.end_span(client,root,project_info.id,root_end)
                    except Exception as error:
                        if isinstance(error,RuntimeError) and str(error)=="SPAN_END_READBACK_PENDING" or getattr(error,"status_code",None)==404:closure_pending=True
                        else:raise
                    if closure_pending:raise RuntimeError("SPAN_END_READBACK_PENDING")
                with self.store.engine.begin() as conn:
                    conn.execute(update(outbox).where(outbox.c.id==row["id"]).values(status="confirmed",attempts=row["attempts"]+1,next_at=None))
                delivered+=1
            except Exception as error:
                with self.store.engine.begin() as conn:
                    conn.execute(update(outbox).where(outbox.c.id==row["id"]).values(status="pending",attempts=row["attempts"]+1,next_at=(datetime.now(timezone.utc)+timedelta(seconds=min(300,2**min(row["attempts"],8)))).isoformat()))
                    allowed={"TRACE_MAPPING_MISMATCH","SPAN_END_READBACK_PENDING","TRACE_PARTITION_ADDRESS_MISSING","EVALUATION_FEEDBACK_READBACK_UNCONFIRMED","EVALUATION_FEEDBACK_SCORE_MISMATCH","RUN_STILL_ACTIVE","AGENT_TRACE_NOT_YET_CREATED"}
                reason=str(error) if isinstance(error,RuntimeError) and str(error) in allowed else None
                self.store.put("telemetry-error",row["id"],{"category":type(error).__name__,"reason":reason,"at":now(),"event_id":row["id"]})
                failed+=1
        if not self.injected:client.close(timeout=0)
        with self.store.engine.connect() as conn:
            remaining=conn.execute(select(func.count()).select_from(outbox).where(outbox.c.status!="confirmed")).scalar()
        return {"status":"pass" if not remaining else "pending","delivered":delivered,"failed":failed,"pending":remaining}

    def coverage(self,rid):
        with self.store.engine.connect() as conn:
            rows=conn.execute(select(outbox.c.status).where(outbox.c.run_id==rid)).scalars().all()
        return sum(x=="confirmed" for x in rows)/len(rows) if rows else None

    def export_experiments(self):
        if not self.config.trace_enabled:return {"status":"disabled"}
        from .experiment_export import export_experiment
        for experiment in self.store.list("experiment"):
            record=self.store.get("experiment-export",experiment["id"])
            if record and record["status"]=="confirmed":continue
            try:
                with self.lock:return export_experiment(self,experiment)
            except Exception as error:
                self.store.put("experiment-export-error",experiment["id"],{"category":type(error).__name__,"at":now()})
                return {"status":"pending","category":type(error).__name__}
        return {"status":"up_to_date"}
