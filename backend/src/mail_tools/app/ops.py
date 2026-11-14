from statistics import mean
from .config import digest
from .contracts import registry, PROMPTS
from .store import now

GATES=[("integrity","Integrity"),("safety","Safety"),("evidence","Evidence"),("quality","Quality"),("reliability","Reliability"),("performance","Performance / Cost"),("observability","Observability"),("recovery","Recovery")]


def manifest(config,agents=None,contracts=None):
    agents=agents or registry(config.model)
    from pathlib import Path
    import hashlib
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
    from mail_tools.settings import ROOT,load_settings
    import subprocess
    locks={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"backend/uv.lock",ROOT/"frontend/package-lock.json") if p.exists()}
    plugins={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"integrations/hermes-mail-runtime").glob("*") if p.is_file()}
    checkout=load_settings().hermes_checkout
    gateway_commit=None
    if checkout:
        resolved=(ROOT/checkout).resolve()
        if resolved.is_relative_to((ROOT/".local").resolve()) and (resolved/".git").exists():
            checked=subprocess.run(["git","-C",str(resolved),"rev-parse","HEAD"],capture_output=True,text=True,timeout=3)
            if checked.returncode==0:gateway_commit=checked.stdout.strip()
    value={"graph":"supervised.mail@0.3.0","policy":"draft-only@0.3.0","priceSnapshot":"openai-mini-2026-11-02","agents":[{"id":a["id"],"version":a["version"],"prompt":a["prompt"],"model":a["model"]} for a in agents],"limits":{"calls":config.max_calls,"tokens":config.token_budget},"code_version":digest(sources),"sources":sources,"rights":{"realMailExport":config.allow_real_mail_export,"gmailDraftWrite":config.allow_gmail_draft_write},"llmMode":config.llm_mode,"schema":"runtime.v1"}
    value.update(runtimeConfig=config.model_dump(mode="json",exclude={"database_dir"}),dependencyLocks=locks,gatewayPlugin=plugins,gatewayCommit=gateway_commit)
    value["releaseId"]="r-"+digest(value)[:16]
    if contracts:
        value.pop("releaseId")
        value["agent_contracts"]=contracts
        value["releaseId"]="r-"+digest(value)[:16]
    return value


def measure(store,jobs,telemetry):
    workload=[j for j in jobs if j.get("purpose") not in ("system","diagnosis","evaluation")]
    finished=[j for j in workload if j["status"] in ("success","review","failed")]
    history=[e for j in jobs for e in store.history(j["id"])]
    leaves=[e["usage"] for e in history if e["type"]=="llm.completed" and "usage" in e]
    known=bool(leaves) and all(x.get("input_tokens") is not None and x.get("output_tokens") is not None for x in leaves)
    tokens=sum(x["input_tokens"]+x["output_tokens"] for x in leaves) if known else None
    costs=[x["input_tokens"]*.75/1_000_000+x["output_tokens"]*4.50/1_000_000 for x in leaves] if known and all(x.get("model","").startswith("gpt-5.4-mini") for x in leaves) else None
    latencies=sorted(j.get("active_ms",0)/1000 for j in finished)
    coverage=[telemetry.coverage(j["id"]) for j in jobs]
    return {"executions":len(workload),"successes":sum(j["status"] in ("success","review") for j in finished),"p95":latencies[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else None,"avgLatency":mean(latencies) if latencies else None,"tokens":tokens,"cost":sum(costs) if costs is not None else None,"coverage":min(coverage) if coverage and all(x is not None for x in coverage) else None}


def assess(store,config,telemetry,rid):
    jobs=[j for j in store.list("job") if j["releaseId"]==rid]
    metrics=measure(store,jobs,telemetry)
    evaluation=next((e for e in store.list("experiment") if e["releaseId"]==rid),None)
    integrity=all(store.integrity(j["id"]) for j in jobs)
    workload=[j for j in jobs if j.get("purpose") not in ("system","diagnosis","evaluation")]
    failed=any(j["status"]=="failed" for j in workload)
    sample=(evaluation or {}).get("count",0)
    proof=store.get("verification",rid)
    manifest_value=store.get("manifest",rid)
    verified=proof if proof and proof.get("manifestHash")==digest(manifest_value) else {}
    checks=verified.get("checks",{})
    baseline_id=verified.get("baselineReleaseId")
    baseline_jobs=[j for j in store.list("job") if j["releaseId"]==baseline_id] if baseline_id else []
    baseline_workload=[j for j in baseline_jobs if j.get("purpose") not in ("system","diagnosis","evaluation")]
    baseline=measure(store,baseline_workload,telemetry) if baseline_workload else None
    operational=measure(store,workload,telemetry)
    cost_ratio=(operational["cost"]/operational["executions"])/(baseline["cost"]/baseline["executions"]) if baseline and operational["executions"] and baseline["executions"] and operational["cost"] is not None and baseline["cost"] else None
    dataset=store.get("dataset",evaluation["datasetVersion"]) if evaluation else None
    locked=bool(evaluation and evaluation.get("split")=="holdout" and evaluation.get("datasetLocked") and dataset and dataset.get("locked") and dataset.get("digest")==digest(dataset["cases"]))
    from .policy import GateInputs,release_gates
    inputs=GateInputs(integrity=integrity,safety=checks.get("safety"),recovery=checks.get("recovery"),
        holdout_count=sample if locked else 0,risk_count=(evaluation or {}).get("riskCount",0) if locked else 0,
        shadow_count=len({j.get("messageHash",j["id"]) for j in workload if j.get("purpose")=="shadow" and j["source"]=="gmail" and j["status"] in ("success","review")}),
        repetitions=(evaluation or {}).get("repetitions",0),stable=(evaluation or {}).get("stable"),
        quality=None if not evaluation or evaluation["status"]=="pending" else evaluation["status"]=="passed",
        success_rate=metrics["successes"]/metrics["executions"] if metrics["executions"] else None,reliability_count=metrics["executions"],unresolved_failure=failed,
        p95=metrics["p95"],cost_ratio=cost_ratio,coverage=metrics["coverage"],capture_verified=checks.get("capture"))
    gates,decision=release_gates(inputs)
    gates[2]["evidence"]=f"holdout {inputs.holdout_count}/300 · risk {inputs.risk_count}/60 · shadow {inputs.shadow_count}/200 · repeat {inputs.repetitions}/3"
    gates[6]["evidence"]="서버 조회 확인 mapping · capture 계약 검증은 별도" if metrics["coverage"]==1 else "전송 대사 미완료"
    technical=decision=="DEBUG_REQUIRED"
    release=store.get("release",rid)
    if not release: raise KeyError(rid)
    release.update(gates=gates,decision=decision)
    if evaluation:release.update(dataset=evaluation["datasetVersion"],evaluator=evaluation["evaluatorVersion"])
    store.put("release",rid,release)
    evidence={"releaseId":rid,"window":"실제 로컬 실행 전체 · 사람 대기 시간 제외","experiment":evaluation,"metrics":{k:metrics[k] for k in ("executions","successes","p95","tokens","cost","coverage")},"diagnosis":{"quality":None,"status":"UNHEALTHY" if technical else "UNKNOWN","hypothesis":"실행 오류 조사 필요" if technical else "운영 배포 판단을 위한 표본과 복구 검증이 부족합니다. 원인 확정 아님.","evidence":["run:"+j["id"] for j in jobs],"nextAction":"실패 trace 조사" if technical else "잠긴 holdout 평가·shadow·복구 검증 수행"}}
    diagnosis=store.get("diagnosis",rid)
    if diagnosis:
        evidence["diagnosis"].update(hypothesis="LLM 원인 가설 (확정 아님): "+diagnosis["hypothesis"],evidence=diagnosis["evidence_ids"],nextAction=diagnosis["recommended_action"])
    return release,evidence,metrics
