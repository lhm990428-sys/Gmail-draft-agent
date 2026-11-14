from datetime import datetime, timezone
import json
import time
from uuid import uuid4
from .config import digest
from .store import now

# Developer regression set, intentionally small and never called a holdout.
DEV_CASES=(
    {"id":"dev-receipt","kind":"reply","reference":"REPLY_REQUIRED","requests":"수신 여부 확인 및 미확정 참석 여부 확인"},
    {"id":"dev-newsletter","kind":"newsletter","reference":"NO_REPLY","requests":"자동 뉴스레터, 회신 불필요"},
)


def evaluate(service,dataset_id=None):
    dataset=service.store.get("dataset",dataset_id) if dataset_id else None
    if dataset_id and (not dataset or not dataset.get("locked") or digest(dataset["cases"])!=dataset["digest"]):raise ValueError("LOCKED_DATASET_INVALID")
    cases=dataset["cases"] if dataset else DEV_CASES
    split=(dataset or {}).get("split","dev")
    dataset_version=dataset_id or "dev-synthetic@"+digest(DEV_CASES)[:16]
    evaluator_version="independent-rubric@0.3.0"
    identifier="eval-"+uuid4().hex
    entries=[];failures=[];rubrics=[];errors=[]
    attempted={}
    baseline=next((e for e in service.store.list("experiment") if e["datasetVersion"]==dataset_version and e["evaluatorVersion"]==evaluator_version and e.get("llmMode")==service.config.llm_mode),None)
    for case in cases:
        custom=None
        if "body" in case:
            from .broker import fixture_mail
            custom=fixture_mail();custom.update(subject=case["subject"],originalBody=case["body"],latestMessageId="eval-"+case["id"])
        response=service.start(kind=case.get("kind","reply"),wait=True,purpose="evaluation",custom_mail=custom)
        rid=response["id"];job=service.store.get("job",rid)
        job["purpose"]="evaluation";service.store.put("job",rid,job)
        mail=service.mail(job["mailId"])
        attempted[case["id"]]=(mail,rid)
        if job["status"]=="failed":
            errors.append({"case":case["id"],"runId":rid,"reason":"workflow_failed"})
            continue
        correct=1. if mail["category"]==case["reference"] else 0.
        if case["reference"]=="NO_REPLY":
            scores={"grounding":None,"completeness":None,"tone":None,"issues":[]}
        else:
            try:
                # Distinct prompt and invocation, not reuse of the online Critic score.
                judge_id="judge-"+uuid4().hex
                service.store.put("job",judge_id,{"id":judge_id,"mailId":mail["id"],"source":"fixture","purpose":"evaluation","subject":"독립 evaluator","parent":rid,"startedAt":now(),"status":"running","decision":"EVALUATING","releaseId":service.release_id,"calls":0,"reserved_tokens":0,"segment_start":time.time()})
                try:
                    scores=service.harness.call("evaluator",{"run_id":judge_id,"mail":mail,"results":{"reference":case,"candidate":mail["draftBody"]}})
                except Exception:
                    judge=service.store.get("job",judge_id);judge.update(status="failed",decision="DEBUG_REQUIRED");service.store.put("job",judge_id,judge)
                    raise
                judge=service.store.get("job",judge_id);judge.update(status="success",decision="EVALUATED");service.store.put("job",judge_id,judge)
            except Exception as error:
                errors.append({"case":case["id"],"runId":rid,"reason":type(error).__name__});continue
        cid=identifier+"-"+case["id"]
        before=next((service.store.get("eval-case",old_id) for old_id in (baseline or {}).get("caseIds",[]) if old_id.endswith("-"+case["id"])),None)
        rubric=[{"criterion":"triage_correct","score":correct,"reason":"고정 reference와 exact match"}]+[{"criterion":key,"score":scores[key],"reason":"독립 평가 프롬프트 / "+("; ".join(scores["issues"]) or "관찰 가능한 결함 보고 없음")} for key in ("grounding","completeness","tone") if scores[key] is not None]
        detail={"id":cid,"caseKey":case["id"],"experimentId":identifier,"input":mail["originalBody"],"reference":case["requests"],"baselineOutput":"기준 실행 없음" if baseline is None else "이전 experiment 집계와 비교; 동일 사례의 baseline 출력은 별도 실행 필요","candidateOutput":mail["draftBody"] or mail["category"],"rubric":rubric,"evaluator":evaluator_version,"dataset":dataset_version,"promptBefore":"N/A","promptAfter":next(a["prompt"] for a in service.manifest["agents"] if a["id"]=="draft"),"runId":rid}
        service.store.put("eval-case",cid,detail);entries.append(detail);rubrics+=rubric
        if before and not before.get("error"):
            detail.update(baselineOutput=before["candidateOutput"],promptBefore=before["promptAfter"])
            service.store.put("eval-case",cid,detail)
        weighted=None if scores["grounding"] is None else .5*scores["grounding"]+.3*scores["completeness"]+.2*scores["tone"]
        if correct<1 or weighted is not None and weighted<.85:
            failures.append({"id":cid,"subject":mail["subject"],"agent":"triage" if correct<1 else "draft","expected":case["requests"],"actual":mail["category"] if correct<1 else "; ".join(scores["issues"]),"score":correct if correct<1 else weighted})
    for error in errors:
        case=next(c for c in cases if c["id"]==error["case"])
        mail,rid=attempted[case["id"]];cid=identifier+"-"+case["id"]
        detail={"id":cid,"caseKey":case["id"],"experimentId":identifier,"input":mail["originalBody"],"reference":case["requests"],"baselineOutput":"미측정","candidateOutput":mail["draftBody"] or "실행 실패 · 결과 미측정","rubric":[],"evaluator":evaluator_version,"dataset":dataset_version,"promptBefore":"N/A","promptAfter":"N/A","runId":rid,"error":error["reason"]}
        service.store.put("eval-case",cid,detail);entries.append(detail)
        failures.append({"id":cid,"subject":mail["subject"],"agent":"runtime","expected":case["requests"],"actual":"평가 미완료: "+error["reason"],"score":None})
    thresholds={"triage_correct":.90,"grounding":.90,"completeness":.85,"tone":.80}
    metrics=[]
    for key,threshold in thresholds.items():
        scores=[r["score"] for r in rubrics if r["criterion"]==key]
        value=sum(scores)/len(scores) if scores and not errors else None
        previous=next((m["candidate"] for m in (baseline or {}).get("metrics",[]) if m["key"]==key),None)
        metrics.append({"key":key,"label":key,"baseline":previous,"candidate":value,"threshold":threshold})
    status="pending" if errors or any(m["candidate"] is None for m in metrics) else "passed" if all(m["candidate"]>=m["threshold"] for m in metrics) else "regression"
    previous=[e for e in service.store.list("experiment") if e["releaseId"]==service.release_id and e["datasetVersion"]==dataset_version and e["evaluatorVersion"]==evaluator_version and not e.get("errors")]
    repeats=len(previous)+1 if not errors else 0
    recent=previous[:2]
    stable=None if len(recent)<2 or errors else all(m["candidate"] is not None and all(next((v["candidate"] for v in old["metrics"] if v["key"]==m["key"]),None) is not None and abs(next(v["candidate"] for v in old["metrics"] if v["key"]==m["key"])-m["candidate"])<=.03 for old in recent) for m in metrics)
    result={"id":identifier,"name":"개발용 합성 회귀 평가 (holdout 아님)" if split=="dev" else "잠긴 합성 holdout 평가","releaseId":service.release_id,"dataset":dataset_version,"datasetVersion":dataset_version,"evaluatorVersion":evaluator_version,"count":len(cases),"status":status,"metrics":metrics,"failures":failures,"errors":errors,"caseIds":[e["id"] for e in entries],"createdAt":now(),"model":service.config.model,"llmMode":service.config.llm_mode,"split":split,"datasetLocked":True,"riskCount":sum(c.get("risk",False) for c in cases),"repetitions":repeats,"stable":stable}
    service.store.put("experiment",identifier,result)
    if dataset is None:service.store.put("dataset",dataset_version,{"id":dataset_version,"digest":digest(DEV_CASES),"cases":list(DEV_CASES),"purpose":"dev_regression","locked":True,"split":"dev"})
    # Each measured case score is placed in durable telemetry outbox via boundary events.
    for entry in entries:
        service.store.emit(entry["runId"],"checkpoint","eval.completed","done","개발 회귀 점수 저장 · holdout 증거로 대체하지 않음",evaluation={"experimentId":identifier,"datasetVersion":dataset_version,"evaluatorVersion":evaluator_version,"rubric":entry["rubric"]})
    return {"id":identifier}
