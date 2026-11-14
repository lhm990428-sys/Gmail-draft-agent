"""Explicit, bounded integration probes; never invoked by doctor or import."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from .settings import Settings
from .secrets import get_secret, put_secret

READONLY = "https://www.googleapis.com/auth/gmail.readonly"


def openai_probe(settings: Settings) -> dict:
    if settings.llm_provider != "openai" or not settings.llm_model:
        raise ValueError("Configure OpenAI provider/model first")
    key = get_secret("openai-api-key")
    if not key:
        raise ValueError("Store openai-api-key first")
    from openai import OpenAI
    from langsmith import tracing_context
    started = time.monotonic()
    # Fixed synthetic input. No tools, no conversation storage, no retries.
    with tracing_context(enabled=False), OpenAI(api_key=key, base_url="https://api.openai.com/v1", max_retries=0, timeout=25) as client:
        response = client.responses.create(
            model=settings.llm_model,
            input="Connection test using synthetic data. Reply with only OK.",
            max_output_tokens=64, store=False, reasoning={"effort": "none"},
        )
    usage = response.usage
    if response.status != "completed" or "OK" not in response.output_text.upper():
        raise RuntimeError("Synthetic model response did not complete as expected")
    return {"status": "pass", "source": "synthetic", "provider": "openai",
            "requested_model": settings.llm_model, "reported_model": response.model,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "input_tokens": usage.input_tokens if usage else None,
            "output_tokens": usage.output_tokens if usage else None,
            "request_id": response._request_id, "cost": None}


def langsmith_probe(settings: Settings) -> dict:
    if os.getenv("LANGSMITH_RUNS_ENDPOINTS") or os.getenv("LANGCHAIN_RUNS_ENDPOINTS"):
        raise ValueError("Multi-endpoint trace replication is not allowed in this setup profile")
    key = get_secret("langsmith-api-key")
    if not key:
        raise ValueError("Store langsmith-api-key first")
    from langsmith import Client
    client = Client(api_url=settings.langsmith_endpoint, api_key=key,
                    workspace_id=settings.langsmith_workspace_id or None,
                    hide_inputs=True, hide_outputs=True, auto_batch_tracing=False,
                    tracing_mode="langsmith", otel_enabled=False, omit_traced_runtime_info=True,
                    timeout_ms=10000)
    run_id, feedback_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    # Allowlisted metadata only. Caller cannot supply free-form content or errors.
    client.create_run(id=run_id, name="synthetic-setup-probe", run_type="chain",
                      inputs={}, outputs={}, start_time=now, end_time=now,
                      project_name=settings.langsmith_project,
                      extra={"metadata": {"source": "synthetic", "environment": "dev",
                                          "phase": "setup", "schema_version": "setup.v1"}})
    # Poll query consistency without replaying writes.
    confirmed = False
    for attempt in range(5):
        try:
            run = client.read_run(run_id)
            if str(run.id) == str(run_id):
                confirmed = True
                break
        except Exception:
            if attempt == 4:
                raise RuntimeError("Trace submitted but readback unconfirmed; do not claim success") from None
        time.sleep(1)
    if not confirmed:
        raise RuntimeError("Trace submitted but readback unconfirmed")
    client.create_feedback(run_id, "setup_connectivity", score=1.0,
                           feedback_id=feedback_id,
                           stop_after_attempt=1,
                           extend_trace_retention=False,
                           comment="Synthetic SDK connectivity only; not agent quality.")
    for attempt in range(5):
        scores = list(client.list_feedback(run_ids=[run_id], feedback_key=["setup_connectivity"]))
        if any(str(item.id) == str(feedback_id) and item.score == 1.0 for item in scores):
            return {"status": "pass", "source": "synthetic", "run_id": str(run_id),
                    "feedback_id": str(feedback_id), "endpoint": settings.langsmith_endpoint,
                    "project": settings.langsmith_project, "trace_readback": True,
                    "feedback_readback": True, "agent_quality_evaluation": "not_run"}
        time.sleep(1)
    raise RuntimeError("Feedback submitted but readback unconfirmed")


def gmail_auth(path: Path,draft_write=False) -> dict:
    from google_auth_oauthlib.flow import InstalledAppFlow
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    installed = config.get("installed", {})
    # Do not follow arbitrary auth/token endpoints from a supplied JSON file.
    if installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth" or installed.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise ValueError("Expected official Google Desktop OAuth client JSON")
    requested={READONLY}
    if draft_write:requested.add("https://www.googleapis.com/auth/gmail.compose")
    flow = InstalledAppFlow.from_client_config(config, sorted(requested))
    creds = flow.run_local_server(host="127.0.0.1", port=0, timeout_seconds=180,
                                  open_browser=True, access_type="offline", prompt="consent",
                                  authorization_prompt_message="Authorize the test Gmail account in your browser.",
                                  success_message="Authorization received. You may close this tab.")
    granted = set(creds.granted_scopes or creds.scopes or [])
    if granted != requested:
        raise ValueError("Unexpected OAuth scopes; revoke this test authorization")
    if not creds.refresh_token:
        raise ValueError("No refresh token returned; reconnect using test account")
    put_secret("gmail-oauth-token", creds.to_json())
    return {"status": "stored", "scope": "gmail.readonly + gmail.compose" if draft_write else "gmail.readonly", "storage": "Windows Credential Manager","broker_writes_enabled":False}


def gmail_probe() -> dict:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2
    from functools import partial
    from googleapiclient.discovery import build
    token = get_secret("gmail-oauth-token")
    if not token:
        raise ValueError("Run gmail-auth first")
    info = json.loads(token)
    if set(info.get("scopes", [])) != {READONLY} or info.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise ValueError("Token scope/endpoint is not the approved readonly setup profile")
    creds = Credentials.from_authorized_user_info(info, [READONLY])
    if not creds.valid:
        creds.refresh(partial(Request(), timeout=15))
        put_secret("gmail-oauth-token", creds.to_json())
    transport = AuthorizedHttp(creds, http=httplib2.Http(timeout=15))
    service = build("gmail", "v1", http=transport, cache_discovery=False)
    try:
        # No message IDs, bodies, label names, addresses, or draft writes.
        result = service.users().labels().list(userId="me", fields="labels(id,type)").execute(num_retries=0)
    finally:
        service.close()
    return {"status": "pass", "scope": "gmail.readonly", "operation": "labels.list",
            "label_count": len(result.get("labels", [])), "mail_bodies_read": 0,
            "drafts_written": 0, "send_enabled": False}
