import asyncio
from datetime import datetime,timezone
from uuid import uuid5,NAMESPACE_URL
import httpx
from mail_tools.settings import load_settings
from mail_tools.secrets import get_secret
from .config import digest
from .store import now


def export_experiment(telemetry,experiment):
    """Official externally-managed experiment ingestion, using hashes/references only."""
    store=telemetry.store;identifier=experiment["id"]
    existing=store.get("experiment-export",identifier)
    if existing and existing["status"]=="confirmed":return existing
    details=[store.get("eval-case",cid) for cid in experiment["caseIds"]]
    dataset=store.get("dataset",experiment["datasetVersion"])
    if not dataset or not dataset.get("locked") or digest(dataset["cases"])!=dataset["digest"]:raise RuntimeError("DATASET_LOCK_MISMATCH")
    rows=[]
    starts=[]
    for detail in details:
        job=store.get("job",detail["runId"])
        start=datetime.fromisoformat(job["startedAt"]);starts.append(start)
        from datetime import timedelta
        end=start+timedelta(milliseconds=job.get("active_ms",0))
        key=detail.get("caseKey",detail["id"].removeprefix(identifier+"-"))
        reference=next(c["reference"] for c in dataset["cases"] if c["id"]==key)
        rows.append({"row_id":str(uuid5(NAMESPACE_URL,experiment["datasetVersion"]+":"+key)),
            "inputs":{"case_id":key,"input_hash":digest(detail["input"]),"source":"synthetic-"+experiment.get("split","dev")},
            "expected_outputs":{"category":reference},"actual_outputs":{"case_id":key,"candidate_hash":digest(detail["candidateOutput"]),"runtime_run_id":detail["runId"]},
            "evaluation_scores":[{"key":r["criterion"],"score":r["score"],"feedback_source":{"type":"api"}} for r in detail["rubric"]],
            "start_time":start.isoformat(),"end_time":end.isoformat(),"run_name":"synthetic-dev-case",
            "run_metadata":{"release_id":experiment["releaseId"],"runtime_run_id":detail["runId"],"evaluator_version":experiment["evaluatorVersion"],"evaluation_error":detail.get("error"),"llm_mode":experiment["llmMode"]}})
    body={"experiment_name":"hermes-mail-"+identifier,"experiment_description":"Local graph results + independent evaluator scores. Development synthetic set, not production holdout.",
        "dataset_id":str(uuid5(NAMESPACE_URL,experiment["datasetVersion"])),"dataset_name":"hermes-mail-"+experiment["datasetVersion"],"dataset_description":"Locked references only; raw mail content remains local.",
        "experiment_start_time":min(starts).isoformat(),"experiment_end_time":now(),
        "experiment_metadata":{"release_id":experiment["releaseId"],"dataset_version":experiment["datasetVersion"],"evaluator_version":experiment["evaluatorVersion"],"llm_mode":experiment["llmMode"]},
        "summary_experiment_scores":[{"key":m["key"],"score":m["candidate"]} for m in experiment["metrics"] if m["candidate"] is not None],"results":rows}
    settings=load_settings();client=telemetry.client()
    try:
        if existing is None:
            # Durable external intent: response loss is reconciled, not blindly POSTed again.
            store.put("experiment-export",identifier,{"status":"submitted_unknown","requestHash":digest(body),"name":body["experiment_name"],"at":now()})
            headers={"x-api-key":get_secret("langsmith-api-key")}
            if settings.langsmith_workspace_id:headers["x-tenant-id"]=settings.langsmith_workspace_id
            with httpx.Client(timeout=20,trust_env=False,follow_redirects=False) as transport:
                response=transport.post(settings.langsmith_endpoint+"/api/v1/datasets/upload-experiment",headers=headers,json=body)
                response.raise_for_status();result=response.json()
            existing={"status":"pending_readback","name":body["experiment_name"],"projectId":result["experiment"]["id"],"datasetId":result["dataset"]["id"],"at":now()}
            store.put("experiment-export",identifier,existing)
        elif existing["status"]=="submitted_unknown":
            project=client.read_project(project_name=existing["name"])
            existing.update(projectId=str(project.id),datasetId=str(project.reference_dataset_id),status="pending_readback")
            store.put("experiment-export",identifier,existing)
        project=client.read_project(project_id=existing["projectId"],include_stats=True)
        examples=list(client.list_examples(dataset_id=existing["datasetId"],limit=len(rows)+1,include_attachments=False))
        if {e.inputs.get("case_id") for e in examples}!={r["inputs"]["case_id"] for r in rows}:raise RuntimeError("DATASET_READBACK_MISMATCH")
        from langsmith import Langsmith
        with Langsmith(base_url=settings.langsmith_endpoint,api_key=get_secret("langsmith-api-key"),tenant_id=settings.langsmith_workspace_id or None,timeout=5,max_retries=0) as reader:
            runs=list(reader.runs.query(project_ids=[existing["projectId"]],is_root=True,selects=["ID","OUTPUTS"],page_size=100))
        if {r.outputs.get("case_id") for r in runs if r.outputs}!={r["inputs"]["case_id"] for r in rows}:raise RuntimeError("EXPERIMENT_ROWS_NOT_CONFIRMED")
        feedback=[]
        feedback_limit=sum(len(row["evaluation_scores"]) for row in rows)+len(rows)
        for offset in range(0,len(runs),50):
            feedback.extend(client.list_feedback(run_ids=[r.id for r in runs[offset:offset+50]],limit=feedback_limit))
        actual={(str(f.run_id),f.key):f.score for f in feedback}
        lookup={r.outputs["case_id"]:str(r.id) for r in runs}
        for row in rows:
            for score in row["evaluation_scores"]:
                value=actual.get((lookup[row["inputs"]["case_id"]],score["key"]))
                if value is None or abs(value-score["score"])>1e-6:raise RuntimeError("EXPERIMENT_SCORE_NOT_CONFIRMED")
        existing.update(status="confirmed",rows=len(runs),scores=len(feedback),confirmedAt=now())
        store.put("experiment-export",identifier,existing)
        return existing
    finally:client.close(timeout=0)
