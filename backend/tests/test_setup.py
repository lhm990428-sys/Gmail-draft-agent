import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mail_tools.settings import Settings
from mail_tools.smoke import offline_smoke
from mail_tools import probes


def test_sqlite_interrupt_survives_reconstruction():
    assert offline_smoke()["status"] == "pass"


def test_configuration_cannot_redirect_credentials():
    with pytest.raises(ValidationError):
        Settings(langsmith_region="https://attacker.invalid")
    with pytest.raises(ValidationError):
        Settings(api_key="not-allowed-in-config")
    with pytest.raises(ValidationError):
        Settings(environment="prod")
    assert Settings(langsmith_region="us").langsmith_endpoint == "https://api.smith.langchain.com"
    assert Settings(langsmith_region="eu").langsmith_endpoint == "https://eu.api.smith.langchain.com"


def test_oauth_json_cannot_redirect_token_exchange(tmp_path):
    path = tmp_path / "client.json"
    path.write_text(json.dumps({"installed": {"auth_uri": "https://attacker.invalid", "token_uri": "https://oauth2.googleapis.com/token"}}))
    with pytest.raises(ValueError, match="official Google"):
        probes.gmail_auth(path)


def test_gmail_probe_refuses_broad_scope_before_network(monkeypatch):
    monkeypatch.setattr(probes, "get_secret", lambda _: json.dumps({"scopes": ["https://www.googleapis.com/auth/gmail.compose"], "token_uri": "https://oauth2.googleapis.com/token"}))
    with pytest.raises(ValueError, match="approved readonly"):
        probes.gmail_probe()


def test_langsmith_trace_and_feedback_require_readback(monkeypatch):
    monkeypatch.delenv("LANGSMITH_RUNS_ENDPOINTS", raising=False)
    monkeypatch.delenv("LANGCHAIN_RUNS_ENDPOINTS", raising=False)
    sent = {}
    class FakeClient:
        def __init__(self, **kwargs):
            sent["client"] = kwargs
        def create_run(self, **kwargs):
            sent["run"] = kwargs
        def read_run(self, run_id):
            return SimpleNamespace(id=run_id)
        def create_feedback(self, run_id, key, **kwargs):
            sent["feedback"] = kwargs
        def list_feedback(self, **kwargs):
            return [SimpleNamespace(id=sent["feedback"]["feedback_id"], score=1.0)]
    monkeypatch.setattr("langsmith.Client", FakeClient)
    monkeypatch.setattr(probes, "get_secret", lambda _: "synthetic-key")
    result = probes.langsmith_probe(Settings(langsmith_region="us"))
    assert result["trace_readback"] and result["feedback_readback"]
    assert sent["client"]["hide_inputs"] and sent["client"]["hide_outputs"]
    assert sent["run"]["inputs"] == sent["run"]["outputs"] == {}
    assert sent["run"]["extra"]["metadata"]["source"] == "synthetic"


def test_unconfirmed_trace_is_not_success(monkeypatch):
    monkeypatch.delenv("LANGSMITH_RUNS_ENDPOINTS", raising=False)
    monkeypatch.delenv("LANGCHAIN_RUNS_ENDPOINTS", raising=False)
    class Unreadable:
        def __init__(self, **kwargs): pass
        def create_run(self, **kwargs): pass
        def read_run(self, run_id): raise RuntimeError("secret provider body")
        def create_feedback(self, *args, **kwargs): pytest.fail("Must not create feedback before trace confirmation")
    monkeypatch.setattr("langsmith.Client", Unreadable)
    monkeypatch.setattr(probes, "get_secret", lambda _: "synthetic-key")
    monkeypatch.setattr(probes.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="readback unconfirmed"):
        probes.langsmith_probe(Settings(langsmith_region="us"))


def test_environment_cannot_add_trace_recipients(monkeypatch):
    monkeypatch.setenv("LANGSMITH_RUNS_ENDPOINTS", '{"https://attacker.invalid":"fake"}')
    monkeypatch.setattr(probes, "get_secret", lambda _: pytest.fail("Must fail before reading the key"))
    with pytest.raises(ValueError, match="replication"):
        probes.langsmith_probe(Settings(langsmith_region="us"))


def test_openai_request_is_bounded_synthetic_and_fixed_endpoint(monkeypatch):
    sent = {}
    class FakeOpenAI:
        def __init__(self, **kwargs):
            sent["client"] = kwargs
            self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            sent["request"] = kwargs
            return SimpleNamespace(status="completed", output_text="OK", model="synthetic-model",
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=1), _request_id="synthetic-request")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://attacker.invalid")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    monkeypatch.setattr(probes, "get_secret", lambda _: "synthetic-key")
    result = probes.openai_probe(Settings(llm_provider="openai", llm_model="gpt-5.4-mini"))
    assert result["status"] == "pass"
    assert sent["client"]["base_url"] == "https://api.openai.com/v1"
    assert sent["client"]["max_retries"] == 0
    assert sent["request"]["store"] is False
    assert sent["request"]["max_output_tokens"] == 64
    assert "tools" not in sent["request"]


def test_failure_report_only_exposes_allowlisted_diagnostics():
    from mail_tools.cli import failure_report
    class ProviderError(Exception):
        status_code = 429
        code = "insufficient_quota"
    report = failure_report(ProviderError("secret key and raw provider data"))
    assert report["http_status"] == 429
    assert report["error_code"] == "insufficient_quota"
    assert "secret key" not in json.dumps(report)
    class UnknownError(Exception):
        status_code = "private account data"
        code = "private account data"
    report = failure_report(UnknownError("secret"))
    assert "http_status" not in report and "error_code" not in report
