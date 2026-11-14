from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import time
from uuid import uuid4
from sqlalchemy import insert, select, update
from .store import Store, claims, now
from .config import AppConfig, digest
from .contracts import registry
from .models import OpenAIModel, ScriptedModel
from .harness import Harness
from .broker import GmailBroker, FixtureBroker, PolicyDenied, StaleReview, UncertainWrite, fixture_mail, approval_signature
from .telemetry import Telemetry
from .ops import manifest, assess, measure
from .topology import topology


class NotFound(Exception): pass
class Busy(Exception): pass


class Service:
    def __init__(self, config: AppConfig, key: bytes, approval_key: bytes, model=None, telemetry_client=None,agent_registry=None):
        from .ownership import RuntimeOwnership
        self.ownership=RuntimeOwnership(config.database_dir)
        self.config=config;self.approval_key=approval_key
        self.store=Store(config.database_dir,key)
        from .registry import AgentRegistry
        self.registry=agent_registry or AgentRegistry(config.model,economy=config.economy_profile)
        self.model=model or (ScriptedModel(economy=config.economy_profile) if config.llm_mode=="scripted" else OpenAIModel(config,self.registry))
        self.harness=Harness(self.store,config,self.model,self.registry)
        self.gmail=GmailBroker(config,approval_key);self.fixture=FixtureBroker(self.store,approval_key)
        self.telemetry=Telemetry(self.store,config,telemetry_client)
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="mail-runtime")
        self.active_writes=set()
        self.manifest=manifest(config,self.registry.describe(),self.registry.contracts());self.release_id=self.manifest["releaseId"]
        from mail_tools.settings import ROOT
        for target in ("gmail","langsmith","openai","hermes"):
            path=ROOT/".local/reports"/("hermes-probe.json" if target=="hermes" else f"probe-{target}.json")
            if path.exists():
                try:
                    report=json.loads(path.read_text(encoding="utf-8"))
                    self.store.put("connection",target,{"status":report.get("status"),"checkedAt":report.get("checked_at")})
                except (ValueError,OSError):pass
        if not self.store.get("release",self.release_id):
            self.store.put("manifest",self.release_id,self.manifest)
            self.store.put("release",self.release_id,{"id":self.release_id,"version":"0.3.0","state":"candidate","decision":"HOLD","createdAt":now(),"commit":self.release_id,"dataset":"미평가","evaluator":"rubric@0.3.0","gates":[]})
        if not self.store.get("release-artifact",self.release_id):
            import base64,hashlib,inspect
            from pathlib import Path
            from .contracts import PROMPTS,SCHEMAS
            files={p.name:p.read_bytes() for p in Path(__file__).parent.glob("*.py")}
            if any(hashlib.sha256(data).hexdigest()!=self.manifest["sources"][name] for name,data in files.items()):raise RuntimeError("SOURCE_CHANGED_DURING_SNAPSHOT")
            self.store.put("release-artifact",self.release_id,{
                "releaseId":self.release_id,"manifestHash":digest(self.manifest),"createdAt":now(),
                "sourceEncoding":"base64","sources":{name:base64.b64encode(data).decode("ascii") for name,data in files.items()},
                "prompts":{**PROMPTS,**{key:entry.prompt for key,entry in self.registry.entries.items()}},
                "schemas":{key:value.model_json_schema() for key,value in {**SCHEMAS,**{key:entry.schema for key,entry in self.registry.entries.items()}}.items()},
                "factorySources":{key:inspect.getsource(entry.factory) for key,entry in self.registry.entries.items() if entry.factory},
                "locks":{name:(ROOT/name).read_text(encoding="utf-8") for name in self.manifest["dependencyLocks"]}})
        # Process death never silently turns unfinished work into success.
        for job in self.store.list("job"):
            if job["status"]=="running":
                job.update(status="failed",error="PROCESS_RESTART_REQUIRES_EXPLICIT_RETRY")
                self.store.put("job",job["id"],job)
                self.store.emit(job["id"],"checkpoint","run.incomplete","failed","프로세스 재시작 · 명시적 새 실행 필요")
        from .retention import expire_artifacts
        for intent in self.store.list("intent"):
            if intent["status"]=="prepared":
                intent["status"]="uncertain"
                self.store.put("intent",intent["id"],intent)
        expire_artifacts(self)
        from .mailbox import Mailbox
        self.mailbox=Mailbox(self)

    def start(self,source="fixture",kind="reply",parent=None,wait=False,receipt=None,purpose=None,custom_mail=None):
        if source not in ("fixture","gmail"): raise PolicyDenied("UNKNOWN_INPUT_SOURCE")
        with self.store.lock:
            rid="run-"+(digest(receipt)[:32] if receipt else uuid4().hex)
            if receipt and self.store.get("job",rid):return {"id":rid}
            if any(j["status"]=="running" for j in self.store.list("job")): raise Busy("ONE_ACTIVE_WORKFLOW_LIMIT")
            # Gmail data export is opt-in and guarded before any fetch.
            if source=="gmail" and not self.config.allow_real_mail_export:raise PolicyDenied("REAL_MAIL_EXPORT_NOT_APPROVED")
            mail=dict(custom_mail) if custom_mail is not None else self.gmail.read_test_thread() if source=="gmail" else fixture_mail(kind)
            if mail.get("source")!=source:raise PolicyDenied("INPUT_SOURCE_MISMATCH")
            if source=="gmail":
                for previous in self.store.list("mail"):
                    if previous.get("source")=="gmail" and previous.get("threadId")==mail.get("threadId") and previous.get("latestMessageId")!=mail.get("latestMessageId") and previous.get("status")=="waiting":
                        previous["flags"].append("새 수신 도착 · 이전 검토 만료")
                        previous["superseded"]=True;self.store.put("mail",previous["id"],previous)
            mid="mail-"+uuid4().hex
            mail.update(id=mid,runId=rid,preview=mail["originalBody"][:120],category="REVIEW_REQUIRED",confidence=0.,risk="medium",priority="normal",status="waiting",draftBody="",revision=1,flags=["에이전트 처리 중"],draftId=None)
            job={"id":rid,"mailId":mid,"subject":mail["subject"],"source":source,"startedAt":now(),"status":"running","decision":"PROCESSING","releaseId":self.release_id,"calls":0,"reserved_tokens":0,"segment_start":time.time(),"parent":parent}
            if purpose:job["purpose"]=purpose
            job["messageHash"]=digest([mail["latestMessageId"],mail["originalBody"]])
            with self.store.engine.begin() as connection:
                self.store.put("mail",mid,mail,connection);self.store.put("job",rid,job,connection)
                self.store.emit(rid,"gateway","request.received","running","합성 입력 접수" if source=="fixture" else "승인된 Gmail 테스트 라벨 조회",conn=connection,memory={"source":source,"mailRef":mid})
                self.store.emit(rid,"gateway","mail.received","done","정규화 스레드 준비",conn=connection,input=mail["subject"],edgeId="receive")
        if wait: self.execute(rid,mail)
        else: self.executor.submit(self.execute,rid,mail)
        return {"id":rid}

    def execute(self,rid,mail):
        started=time.monotonic()
        try:
            state=self.harness.execute(rid,mail)
            results=state["results"]
            job=self.store.get("job",rid);current=self.store.get("mail",mail["id"])
            triage,risk=results["triage"],results["risk"]
            current.update(category=state["decision"],confidence=triage["confidence"],priority=triage["priority"],risk=risk["risk"],flags=risk["flags"])
            job.update(status="success" if state["decision"]=="NO_REPLY" else "review",decision=state["decision"],active_ms=round((time.monotonic()-started)*1000))
            if state["decision"]=="NO_REPLY":
                current.update(status="rejected",draftBody="")
                self.store.emit(rid,"checkpoint","run.completed","done","회신 불필요 · 작성/쓰기 생략",checkpoint="cp-"+rid,memory={"decision":"NO_REPLY"})
            else:
                current["draftBody"]=results.get("draft",{}).get("body","")
                critique=results.get("critic",{"issues":["위험·불확실성으로 AI 초안 작성 생략 · 사람 확인"]})
                current["flags"]+=critique["issues"]
                if results.get("supervise",{}).get("escalated"): current["flags"].append("Critic 검토 이슈 · 사람 확인 필수")
                self.store.emit(rid,"checkpoint","checkpoint.saved","done","검토 대상 암호화 저장",checkpoint="cp-"+rid,memory={"draft_hash":digest(current["draftBody"]),"revision":str(current["revision"])})
                self.store.emit(rid,"human","review.requested","waiting","사용자 최종 검토 대기",input=current["draftBody"],edgeId="critic-review")
            self.store.put("mail",mail["id"],current);self.store.put("job",rid,job)
        except Exception as error:
            job=self.store.get("job",rid)
            job.update(status="failed",decision="DEBUG_REQUIRED",error=type(error).__name__,active_ms=round((time.monotonic()-started)*1000))
            current=self.store.get("mail",mail["id"]);current["flags"]=["실행 실패 · "+type(error).__name__]
            self.store.put("job",rid,job);self.store.put("mail",mail["id"],current)
            self.store.emit(rid,"checkpoint","run.failed","failed",type(error).__name__,checkpoint="cp-"+rid)

    def mail(self,mid):
        result=self.store.get("mail",mid)
        if result is None: raise NotFound(mid)
        return result

    def audit(self,typ,status,method,route,reference=None):
        # Route templates and decisions only; no URL queries, tokens or request bodies.
        rid="audit-"+digest(self.release_id+now()[:10])[:20]
        with self.store.lock:
            if self.store.get("job",rid) is None:
                self.store.put("job",rid,{"id":rid,"mailId":None,"subject":"운영 경계 감사","source":"fixture","purpose":"system","startedAt":now(),"status":"success","decision":"AUDIT","releaseId":self.release_id,"calls":0,"reserved_tokens":0,"active_ms":0,"segment_start":time.time()})
            self.store.emit(rid,"gateway",typ,status,"로컬 API 인증·운영 경계",memory={"method":method,"route":route,**({"messageRef":reference} if reference else {})})

    def edit(self,mid,revision,body):
        if not body.strip() or len(body)>10000: raise PolicyDenied("DRAFT_BODY_POLICY")
        with self.store.lock:
            mail=self.mail(mid);self._reviewable(mail,revision)
            mail.update(draftBody=body,revision=revision+1)
            self.store.put("mail",mid,mail)
            self.store.emit(mail["runId"],"human","review.edited","waiting","로컬 초안 수정 · 이전 승인 무효",input=body,memory={"revision":str(mail["revision"]),"draft_hash":digest(body)})
            return self.mail_view(mail)

    def _reviewable(self,mail,revision):
        if mail.get("superseded"):raise StaleReview("NEW_MESSAGE_SUPERSEDES_THIS_REVIEW")
        if mail["revision"]!=revision: raise StaleReview("DRAFT_REVISION_CHANGED")
        if mail["status"]!="waiting" or mail.get("intent"):
            raise StaleReview("REVIEW_CLOSED_OR_WRITE_PENDING")
        if self.store.get("job",mail["runId"])["status"]!="review": raise StaleReview("GRAPH_NOT_WAITING_FOR_REVIEW")

    def decide(self,mid,revision,action):
        if action not in ("approve","reject"): raise PolicyDenied("INVALID_REVIEW_ACTION")
        with self.store.lock:
            mail=self.mail(mid);self._reviewable(mail,revision)
            rid=mail["runId"]
            if action=="reject":
                self.harness.resume(rid,"rejected")
                mail["status"]="rejected";self.store.put("mail",mid,mail)
                self.store.emit(rid,"human","review.rejected","done","사용자 거절 · 외부 쓰기 없음")
                self.store.emit(rid,"checkpoint","run.completed","done","검토 종료",checkpoint="cp-"+rid+"-result")
                job=self.store.get("job",rid);job["status"]="success";self.store.put("job",rid,job)
                return {"id":mid,"status":"rejected","draftId":None}
            if mail["source"]=="gmail" and not self.config.allow_gmail_draft_write:
                self.harness.resume(rid,"approved")
                mail["status"]="reviewed";self.store.put("mail",mid,mail)
                job=self.store.get("job",rid);job["status"]="success";self.store.put("job",rid,job)
                self.store.emit(rid,"human","review.completed","done","앱 내부 검토 완료 · Gmail 저장·발송 없음")
                self.store.emit(rid,"checkpoint","run.completed","done","검토 종료",checkpoint="cp-"+rid+"-result")
                return {"id":mid,"status":"reviewed","draftId":None}
            if not mail["draftBody"].strip(): raise PolicyDenied("EMPTY_DRAFT")
            broker=self.gmail if mail["source"]=="gmail" else self.fixture
            broker.preflight(mail)
            approval={"mail_id":mid,"revision":revision,"draft_hash":digest(mail["draftBody"]),"recipient_hash":digest(mail["address"]),"message_id":mail["latestMessageId"],"expires":time.time()+300,"actor":"local-human","nonce":uuid4().hex}
            signature=approval_signature(self.approval_key,approval)
            intent=uuid4().hex
            # Durable intent exists before any write; only one intent per review.
            mail["intent"]=intent
            with self.store.engine.begin() as connection:
                self.store.put("mail",mid,mail,connection)
                self.store.put("intent",intent,{"id":intent,"status":"prepared","approval":approval,"signature":signature,"mailId":mid},connection)
                self.store.emit(rid,"human","review.approved","done","사용자 승인 snapshot 고정",conn=connection,memory={"revision":str(revision),"draft_hash":approval["draft_hash"]},edgeId="approval")
                self.store.emit(rid,"broker","write.intent","running","내구성 intent 저장 · create 재시도 금지",conn=connection,memory={"intent":intent,"source":mail["source"]})
            self.active_writes.add(intent)
        try:
            draft_id=broker.create_draft(mail,approval,signature,intent)
        except Exception:
            with self.store.lock:
                record=self.store.get("intent",intent);record["status"]="uncertain";self.store.put("intent",intent,record)
                mail["flags"].append("응답 유실 가능 · 저장 결과 대사 필요");self.store.put("mail",mid,mail)
                self.store.emit(rid,"broker","write.uncertain","uncertain","쓰기 결과 미확정 · 자동 재생성 금지")
                raise UncertainWrite("WRITE_UNCERTAIN_RECONCILE_REQUIRED") from None
        else:
            with self.store.lock:return self._confirmed(mail,draft_id,intent)
        finally:
            with self.store.lock:self.active_writes.discard(intent)

    def _confirmed(self,mail,draft_id,intent):
        rid=mail["runId"]
        record=self.store.get("intent",intent);record.update(status="confirmed",draftId=draft_id);self.store.put("intent",intent,record)
        mail.update(status="draft_saved",draftId=draft_id);self.store.put("mail",mail["id"],mail)
        self.store.emit(rid,"broker","write.confirmed","done","Gmail Draft 저장 확인" if mail["source"]=="gmail" else "로컬 합성 Draft 저장 확인",memory={"draftRef":digest(draft_id),"write":"draft-only"})
        resume_ok=True
        try: self.harness.resume(rid,"approved")
        except Exception:
            # Confirmed external side effect must not be retried when checkpoint resume fails.
            self.store.emit(rid,"checkpoint","checkpoint.resume_failed","failed","쓰기는 확인됨 · graph 재개 복구 필요")
            resume_ok=False
        if resume_ok:self.store.emit(rid,"checkpoint","run.completed","done","처리 결과 기록",checkpoint="cp-"+rid+"-result")
        job=self.store.get("job",rid);job["status"]="success" if resume_ok else "failed"
        if not resume_ok:job.update(decision="DEBUG_REQUIRED",error="CHECKPOINT_RESUME_AFTER_CONFIRMED_WRITE")
        self.store.put("job",rid,job)
        return {"id":mail["id"],"status":"draft_saved","draftId":draft_id}

    def reconcile(self,mid):
        with self.store.lock:
            mail=self.mail(mid);intent=mail.get("intent")
            if not intent: raise StaleReview("NO_PENDING_INTENT")
            if intent in self.active_writes:raise Busy("WRITE_IN_PROGRESS")
            record=self.store.get("intent",intent)
            if record["status"]=="confirmed": return {"id":mid,"status":"draft_saved","draftId":record["draftId"]}
            broker=self.gmail if mail["source"]=="gmail" else self.fixture
            draft_id=broker.reconcile(mail,intent)
            return self._confirmed(mail,draft_id,intent)

    def retry(self,rid):
        old=self.store.get("job",rid)
        if not old: raise NotFound(rid)
        if old["status"]!="failed": raise StaleReview("ONLY_FAILED_RUN_CAN_RETRY")
        if old.get("purpose") in ("evaluation","diagnosis","system"):raise PolicyDenied("REPEAT_EVALUATION_OR_DIAGNOSIS_FROM_OPS_ACTION")
        if old.get("mailId") and self.mail(old["mailId"]).get("intent"): raise StaleReview("EXISTING_WRITE_INTENT_REQUIRES_RECOVERY_NOT_RETRY")
        return self.start(source=old["source"],parent=rid,purpose=old.get("purpose"),custom_mail=self.mail(old["mailId"]))

    def diagnose(self):
        with self.store.lock:
            if any(j["status"]=="running" for j in self.store.list("job")): raise Busy("ONE_ACTIVE_WORKFLOW_LIMIT")
            rid="ops-"+uuid4().hex
            release,evidence,_=assess(self.store,self.config,self.telemetry,self.release_id)
            job={"id":rid,"mailId":None,"subject":"LLMOps 건강 진단","source":"fixture","purpose":"diagnosis","startedAt":now(),"status":"running","decision":"DIAGNOSING","releaseId":self.release_id,"calls":0,"reserved_tokens":0,"segment_start":time.time()}
            self.store.put("job",rid,job)
        started=time.monotonic()
        try:
            # Only counters, rule results and opaque IDs; no mail bodies or model IO.
            result=self.harness.call("diagnose",{"run_id":rid,"mail":{"subject":"운영 집계"},"results":{"metrics":evidence["metrics"],"gates":release["gates"],"evidence_ids":evidence["diagnosis"]["evidence"]}})
            allowed=set(evidence["diagnosis"]["evidence"])
            result["evidence_ids"]=[x for x in result["evidence_ids"] if x in allowed]
            self.store.put("diagnosis",self.release_id,{**result,"runId":rid,"at":now(),"ruleDecision":release["decision"]})
            self.store.emit(rid,"diagnose","diagnosis.created","done","원인 가설 저장 · 규칙/배포 권한 없음",memory={"hypothesis":result["hypothesis"],"ruleDecision":release["decision"]})
            job=self.store.get("job",rid);job.update(status="success",decision="DIAGNOSIS_RECORDED",active_ms=round((time.monotonic()-started)*1000));self.store.put("job",rid,job)
            return {"id":rid}
        except Exception as error:
            job=self.store.get("job",rid);job.update(status="failed",decision="DEBUG_REQUIRED",error=type(error).__name__);self.store.put("job",rid,job)
            self.store.emit(rid,"diagnose","diagnosis.failed","failed",type(error).__name__)
            raise

    @staticmethod
    def mail_view(mail):
        fields=("id","sender","address","subject","preview","receivedAt","category","confidence","risk","priority","status","originalBody","draftBody","revision","runId","flags","latestMessageId","source","draftId")
        return {k:mail.get(k) for k in fields}

    def runtime(self,rid):
        job=self.store.get("job",rid)
        if not job: raise NotFound(rid)
        return topology(rid,job["source"],self.store.history(rid),self.registry)

    def snapshot(self):
        release,evidence,metrics=assess(self.store,self.config,self.telemetry,self.release_id)
        jobs=[j for j in self.store.list("job") if j.get("purpose")!="system"];runs=[];agents=self.registry.describe()
        for job in jobs:
            history=self.store.history(job["id"])
            leaves=[e for e in history if e["type"]=="llm.completed"]
            measured=measure(self.store,[job],self.telemetry)
            spans=[]
            for e in history:
                if e["type"] in ("llm.completed","llm.failed","review.requested","write.confirmed"):
                    usage=e.get("usage",{})
                    spans.append({"id":e["id"],"parentId":job["id"],"name":e["type"],"agentId":e["nodeId"],"type":"llm" if e["type"].startswith("llm") else "review" if e["nodeId"]=="human" else "tool","status":"error" if e["status"]=="failed" else "waiting" if e["status"]=="waiting" else "success","durationMs":usage.get("duration_ms",0),"inputTokens":usage.get("input_tokens"),"outputTokens":usage.get("output_tokens"),"input":"로컬 이벤트 원장에서 조회","output":e.get("output",e["summary"]),"attempt":e.get("attempt",1)})
            runs.append({"id":job["id"],"subject":job["subject"],"startedAt":job["startedAt"],"status":job["status"],"decision":job["decision"],"latency":job.get("active_ms",0)/1000,"tokens":measured["tokens"],"cost":measured["cost"],"releaseId":job["releaseId"],"plan":(["Supervisor CODE","Triage AI","Context/Risk CODE","optional Draft → Critic","Human review"] if self.config.economy_profile and job["releaseId"]==self.release_id else ["Supervisor plan","Context","Triage ∥ Risk","Draft → Critic","Human review"]),"spans":spans,"events":[{"id":e["id"],"sequence":e["sequence"],"time":e["time"],"type":e["type"],"actor":e["nodeId"],"detail":e["summary"],"status":e["status"],"spanId":e["id"]} for e in history]})
        for agent in agents:
            leafs=[e for j in jobs for e in self.store.history(j["id"]) if e["nodeId"]==agent["id"] and e["type"]=="llm.completed"]
            agent["calls"]=len(leafs)
            agent["latency"]=sum(e["usage"]["duration_ms"] for e in leafs)/max(1,len(leafs))/1000
        coverage=metrics["coverage"]
        health=[
            {"id":"quality","label":"품질","status":"DEGRADED" if evidence["experiment"] and evidence["experiment"]["status"]=="regression" else "UNKNOWN","value":"개발 회귀 평가" if evidence["experiment"] else "미평가","target":"잠긴 holdout / 버전된 점수"},
            {"id":"reliability","label":"기술 안정성","status":"UNHEALTHY" if any(g["id"]=="reliability" and g["status"]=="FAIL" for g in release["gates"]) else "UNKNOWN","value":str(metrics["successes"])+" / "+str(metrics["executions"]),"target":"성공률 >=.98 / n>=200"},
            {"id":"dependencies","label":"인증·도구","status":"UNKNOWN","value":"이전 연결 점검과 현재 건강 probe는 별도","target":"최신 auth/tool probe"},
            {"id":"budget","label":"예산·감독 통제","status":"UNKNOWN" if metrics["tokens"] is None else "HEALTHY","value":"최대 3회 호출 / 자동 재작성 없음 / 누적 금액 제한 없음" if self.config.economy_profile else "12 calls / 동시 3 / 재작성 2 상한 · token 보장 별도","target":"provider usage / 입력 상한 검증"},
            {"id":"performance","label":"성능·비용","status":"UNKNOWN","value":"p95 "+("N/A" if metrics["p95"] is None else str(round(metrics["p95"],2))+"s")+" / 비용 baseline 미확정","target":"p95<=30s / cost<=baseline+20%"},
            {"id":"observability","label":"이벤트 대사","status":"UNKNOWN","value":"delivery "+("N/A" if coverage is None else str(round(coverage,4)))+" / capture 계약 검증 별도","target":"capture + delivery =1.00"},
            {"id":"recovery","label":"복구·재현","status":"UNKNOWN","value":"개발 회귀 통과와 릴리스별 검증은 별도","target":"manifest별 복구 suite"},
        ]
        dependencies=[]
        for target in ("gmail","langsmith","openai","hermes"):
            record=self.store.get("connection",target)
            dependencies.append({"id":target,"name":target,"status":"ready" if record and record.get("status")=="pass" else "unknown","description":"마지막 연결 점검 근거 · 실시간 건강은 별도","checkedAt":(record or {}).get("checkedAt") or now()})
        archived=[r for r in self.store.list("release") if r["id"]!=self.release_id]
        return {"schemaVersion":"console.v1","environment":"staging","generatedAt":now(),"metrics":metrics,"trend":[],"agents":agents,"mails":[self.mail_view(m) for m in self.store.list("mail")],"runs":runs,"experiments":self.store.list("experiment"),"releases":[release,*archived],"health":health,"incidents":[{"id":"incident-"+j["id"],"title":"실행 실패","severity":"critical","agent":"runtime","cause":"원인 미확정: "+j.get("error","UNKNOWN"),"evidence":[j["id"]],"action":"이벤트/trace 조사 후 명시적 새 실행","runId":j["id"]} for j in jobs if j["status"]=="failed"],"dependencies":dependencies,"capabilities":{"phase":4,"input":"gmail" if self.config.automatic_mail else "fixture","modelMode":self.config.llm_mode,"realMailExport":self.config.allow_real_mail_export,"gmailDraftWrite":self.config.allow_gmail_draft_write,"automaticMail":self.config.automatic_mail,"economyProfile":self.config.economy_profile}}

    def close(self):
        self.mailbox.close()
        self.executor.shutdown(wait=True,cancel_futures=True)
        self.harness.close();self.store.close()
        self.ownership.close()
