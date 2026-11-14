from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import operator
import sqlite3
import time
import threading
from typing import Annotated, TypedDict
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command
from langsmith import tracing_context
from .contracts import registry, PROMPTS
from .config import digest
from .store import now


def merge(left, right): return {**left, **right}


class State(TypedDict, total=False):
    run_id: str
    mail: dict
    results: Annotated[dict, merge]
    rewrites: int
    decision: str


class WorkerOutput(TypedDict):
    results: Annotated[dict, merge]


class Harness:
    def __init__(self, store, config, model,registry=None):
        self.store,self.config,self.model = store,config,model
        from .registry import AgentRegistry
        self.registry=registry or AgentRegistry(config.model)
        self.call_slots=threading.BoundedSemaphore(3)
        connection = sqlite3.connect(store.directory / "checkpoints.sqlite", check_same_thread=False, timeout=15)
        connection.execute("PRAGMA journal_mode=WAL")
        self.connection = connection
        self.saver = SqliteSaver(connection, serde=store.serde)
        self.graph = self._build_economy() if config.economy_profile else self._build()

    def _build_economy(self):
        graph=StateGraph(State)
        def plan(state):
            self.store.emit(state["run_id"],"supervisor","supervisor.plan.validated","done","코드 감독 · 분류 1회 / 필요 시 Draft·Critic 각 1회",memory={"plan":"context → triage → risk → optional draft → critic → human","implementation":"code"})
            return {"results":{"supervisor":{"agents":["context","triage","risk","draft","critic"],"reason":"비용 절약 DAG · 코드 감독"},"context":{"facts":[],"requests":[],"unknowns":[],"evidence":[state["mail"]["latestMessageId"]]}}}
        graph.add_node("plan",plan)
        for role in ("triage","draft","critic"):
            child=StateGraph(State,output_schema=WorkerOutput)
            def invoke(state,role=role):
                self.store.emit(state["run_id"],role,"task.dispatched","queued","t-"+role,edgeId="dispatch-"+role)
                return {"results":{role:self.call(role,state)}}
            child.add_node("specialist",invoke);child.add_edge(START,"specialist");child.add_edge("specialist",END)
            graph.add_node(role,child.compile())
        def route(state):
            triage=state["results"]["triage"]
            decision=triage["category"]
            high=triage.get("injection",False) or triage.get("risk")=="high"
            if high or triage["confidence"]<.75:decision="REVIEW_REQUIRED"
            risk={"risk":triage.get("risk","medium"),"flags":["사람 검토 필요"] if decision=="REVIEW_REQUIRED" else [],"injection":triage.get("injection",False),"reason":"분류 신호를 검증한 코드 정책"}
            context={"facts":[triage.get("summary",state["mail"]["subject"])],"requests":triage.get("requests",[]),"unknowns":[],"evidence":triage.get("evidence",[state["mail"]["latestMessageId"]])}
            self.store.emit(state["run_id"],"context","context.normalized","done","분류 호출의 근거 요약 · 별도 LLM 없음",memory={k:json.dumps(v,ensure_ascii=False) for k,v in context.items()})
            self.store.emit(state["run_id"],"risk","policy.checked","done","위험·불확실성 코드 분기 · 별도 위험 LLM 없음",memory={k:json.dumps(v,ensure_ascii=False) for k,v in risk.items()})
            self.store.emit(state["run_id"],"supervisor","task.joined","done","코드 감독 분류 결과 검증",memory={"decision":decision})
            return {"decision":decision,"results":{"risk":risk,"context":context}}
        graph.add_node("route",route)
        def supervise(state):
            critique=state["results"]["critic"]
            self.store.emit(state["run_id"],"critic","critic.reviewed","done","자동 재작성 없이 사람 검토",edgeId="critic-review")
            return {"results":{"supervise":{"action":"review","reason":"사람 최종 검토","escalated":critique["verdict"]!="pass"}}}
        graph.add_node("supervise",supervise)
        def review(state):
            action=interrupt({"kind":"human-review","run_id":state["run_id"],"draft_hash":digest(state["results"].get("draft",{}).get("body",""))})
            if action not in ("approved","rejected"):raise RuntimeError("INVALID_RESUME_ACTION")
            return {"results":{"human":{"decision":action}}}
        graph.add_node("human_review",review)
        graph.add_edge(START,"plan");graph.add_edge("plan","triage");graph.add_edge("triage","route")
        graph.add_conditional_edges("route",lambda s:s["decision"],{"NO_REPLY":END,"REVIEW_REQUIRED":"human_review","REPLY_REQUIRED":"draft"})
        graph.add_edge("draft","critic");graph.add_edge("critic","supervise");graph.add_edge("supervise","human_review");graph.add_edge("human_review",END)
        return graph.compile(checkpointer=self.saver)

    def call(self, role, state):
        rid = state["run_id"]
        public_role = "supervisor" if role == "supervise" else "critic" if role=="evaluator" else role
        results=state.get("results",{})
        mail={k:state["mail"].get(k) for k in ("subject","originalBody","latestMessageId") if k in state["mail"]}
        payload={"mail":mail,"results":results,"rewrites":state.get("rewrites",0)}
        if role=="supervisor": payload={"subject":mail.get("subject"),"goal":"회신 분류 및 사람 검토용 초안 준비","registry":list(self.registry.worker_ids)}
        if role=="context": payload={"mail":mail}
        if role in ("triage","risk"):
            payload={"mail":mail,"context":results.get("context",{})}
        if role=="draft": payload={"mail":mail,"results":{k:results[k] for k in ("context","triage","risk","critic") if k in results}}
        if role=="critic": payload={"mail":mail,"results":{k:results[k] for k in ("context","draft") if k in results}}
        if role=="supervise": payload={"results":{k:results[k] for k in ("triage","risk","critic") if k in results},"rewrites":state.get("rewrites",0)}
        if role in self.registry.entries and role not in ("supervisor","context","triage","risk","draft","critic","diagnose"):
            payload={"mail":mail,"results":{k:results[k] for k in self.registry.entries[role].context_keys if k in results}}
        # Locked reservations prevent parallel workers overspending the call cap.
        with self.store.lock:
            job = self.store.get("job",rid)
            if job is None: raise RuntimeError("RUN_NOT_ADMITTED")
            if time.time()-job["segment_start"] > self.config.active_timeout_seconds: raise TimeoutError("RUN_DEADLINE")
            calls = job.get("calls",0)
            prompt=self.registry.entries[role].prompt if role in self.registry.entries else PROMPTS[role]
            estimate = len(json.dumps(payload,ensure_ascii=False).encode()) + len(prompt.encode()) + self.config.max_output_tokens + 1800
            if calls >= self.config.max_calls or job.get("reserved_tokens",0)+estimate > self.config.token_budget:
                raise RuntimeError("RUN_BUDGET_EXHAUSTED")
            today = now()[:10]
            used = sum(j.get("calls",0) for j in self.store.list("job") if j["startedAt"][:10]==today)
            if used >= self.config.daily_call_limit: raise RuntimeError("DAILY_CALL_LIMIT")
            job.update(calls=calls+1,reserved_tokens=job.get("reserved_tokens",0)+estimate)
            self.store.put("job",rid,job)
        start = self.store.emit(rid,public_role,"llm.started","running",role+" 구조화 호출",input=json.dumps(payload,ensure_ascii=False), attempt=calls+1)
        try:
            with self.call_slots,tracing_context(enabled=False): result, usage = self.model.invoke(role,payload)
            if role in self.registry.entries:result=self.registry.entries[role].schema.model_validate(result).model_dump()
        except Exception as error:
            self.store.emit(rid,public_role,"llm.failed","failed",type(error).__name__,errorCategory=type(error).__name__)
            raise
        usage["role"] = role
        self.store.emit(rid,public_role,"llm.completed","done",role+" 결과 검증 완료",output=json.dumps(result,ensure_ascii=False),memory={k:json.dumps(v,ensure_ascii=False) for k,v in result.items()}, usage=usage, startedEventId=start["id"])
        with self.store.lock:
            job = self.store.get("job",rid)
            actual = (usage.get("input_tokens") or 0)+(usage.get("output_tokens") or 0)
            # Missing provider usage remains unknown; never fabricate measured tokens.
            budget_charge = actual if usage.get("input_tokens") is not None else (len(json.dumps(payload,ensure_ascii=False).encode())+len(json.dumps(result,ensure_ascii=False).encode()))//2+400 if self.config.llm_mode=="scripted" else estimate
            job["reserved_tokens"] = max(0,job["reserved_tokens"]-estimate)+budget_charge
            self.store.put("job",rid,job)
        return result

    def _build(self):
        graph = StateGraph(State)
        def plan(state):
            result = self.call("supervisor",state)
            self.registry.validate_plan(result["agents"])
            self.store.emit(state["run_id"],"supervisor","supervisor.plan.validated","done","필수 DAG / 병렬 의존성 / 등록 agent 검증",memory={"plan":json.dumps(result["agents"]),"limits":"12 calls / depth 2 / concurrency 3 / rewrite <=2"})
            return {"results":{"supervisor":result}}
        graph.add_node("supervisor_plan",plan)
        for role in self.registry.worker_ids:
            if self.registry.entries[role].factory:
                graph.add_node(role,self.registry.entries[role].factory(self))
                continue
            child = StateGraph(State,output_schema=WorkerOutput)
            def invoke(state, role=role):
                self.store.emit(state["run_id"],role,"task.dispatched","queued","t-"+role,edgeId="dispatch-"+role)
                result = self.call(role,state)
                return {"results":{role:result}}
            child.add_node("specialist",invoke)
            child.add_edge(START,"specialist");child.add_edge("specialist",END)
            graph.add_node(role,child.compile())
        def join(state):
            result = state["results"]
            if "triage" not in result or "risk" not in result: raise RuntimeError("INCOMPLETE_PARALLEL_JOIN")
            decision = result["triage"]["category"]
            if result["risk"]["injection"] or result["risk"]["risk"]=="high": decision="REVIEW_REQUIRED"
            self.store.emit(state["run_id"],"supervisor","task.joined","done","Triage/Risk 병렬 결과 합류",memory={"decision":decision})
            return {"decision":decision}
        graph.add_node("join",join)
        def supervise(state):
            result = self.call("supervise",state) if state.get("rewrites",0)<2 else {"action":"escalate","reason":"재작성 2회 상한 · 추가 LLM 호출 없이 사람 이관"}
            critique = state["results"]["critic"]
            requires_revision = critique["verdict"]=="revise" or result["action"]=="revise"
            rewrites = state.get("rewrites",0)
            action = "revise" if requires_revision and rewrites<2 else "review"
            self.store.emit(state["run_id"],"critic","critic.rework" if action=="revise" else "critic.reviewed","done","수정 요청" if action=="revise" else "사람 검토 이관",edgeId="rework" if action=="revise" else "critic-review")
            return {"rewrites":rewrites+1 if action=="revise" else rewrites,"results":{"supervise":{**result,"action":action,"escalated":critique["verdict"]!="pass" or result["action"]=="escalate"}}}
        graph.add_node("supervise_review",supervise)
        def review(state):
            # No event writes before interrupt: node replays from the beginning.
            action = interrupt({"kind":"human-review","run_id":state["run_id"],"draft_hash":digest(state["results"]["draft"]["body"])})
            if action not in ("approved","rejected"): raise RuntimeError("INVALID_RESUME_ACTION")
            return {"results":{"human":{"decision":action}}}
        graph.add_node("human_review",review)
        graph.add_edge(START,"supervisor_plan");graph.add_edge("supervisor_plan","context")
        graph.add_edge("context","triage");graph.add_edge("context","risk")
        for role in self.registry.extensions:graph.add_edge("context",role)
        graph.add_edge(["triage","risk",*self.registry.extensions],"join")
        graph.add_conditional_edges("join",lambda s:"end" if s["decision"]=="NO_REPLY" else "draft",{"end":END,"draft":"draft"})
        graph.add_edge("draft","critic");graph.add_edge("critic","supervise_review")
        graph.add_conditional_edges("supervise_review",lambda s:s["results"]["supervise"]["action"],{"revise":"draft","review":"human_review"})
        graph.add_edge("human_review",END)
        return graph.compile(checkpointer=self.saver)

    def execute(self, rid, mail):
        with tracing_context(enabled=False):
            return self.graph.invoke({"run_id":rid,"mail":mail,"results":{},"rewrites":0}, {"configurable":{"thread_id":rid},"recursion_limit":40,"max_concurrency":3})

    def resume(self, rid, decision):
        with tracing_context(enabled=False):
            return self.graph.invoke(Command(resume=decision),{"configurable":{"thread_id":rid},"recursion_limit":40,"max_concurrency":3})

    def state(self,rid):
        return self.graph.get_state({"configurable":{"thread_id":rid}},subgraphs=True)

    def close(self): self.connection.close()
