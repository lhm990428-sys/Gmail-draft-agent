import argparse
from datetime import datetime, timezone
import getpass
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import warnings

from .settings import ROOT, load_settings
from .secrets import NAMES, get_secret, put_secret, delete_secret


def failure_report(error: Exception) -> dict:
    # Never serialize SDK messages, request objects, headers, or error bodies.
    result = {"status": "failed", "category": type(error).__name__,
              "message": "Check configuration/credential access and the setup guide. Raw exception suppressed."}
    if isinstance(error, RuntimeError) and error.args == ("HERMES_GATEWAY_PORT_IN_USE",):
        result.update(code="HERMES_GATEWAY_PORT_IN_USE", message="Hermes 시작 실패: 8642 포트가 이미 사용 중입니다. 이전 실행 창에서 Ctrl+C로 종료한 뒤 다시 실행하세요. 해결되지 않으면 포트 소유 프로세스를 확인해야 합니다.")
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        result["http_status"] = status
    code = getattr(error, "code", None)
    if isinstance(code, str) and code in {
        "insufficient_quota", "rate_limit_exceeded", "invalid_api_key",
        "model_not_found", "permission_denied", "billing_hard_limit_reached",
        "billing_not_active", "invalid_project", "unsupported_value",
    }:
        result["error_code"] = code
    return result


def save_report(report: dict, command: str, target: str = "") -> None:
    directory = ROOT / ".local/reports"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = "-" + target if command == "probe" else ""
    (directory / f"{command}{suffix}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def doctor(settings) -> dict:
    dependencies = {name: version(name) for name in (
        "langgraph", "langgraph-checkpoint-sqlite", "langsmith", "langchain-openai",
        "openai", "fastapi", "sqlalchemy", "alembic", "google-api-python-client", "keyring",
    )}
    secrets = {}
    for name in NAMES:
        try:
            secrets[name] = "present_not_validated" if get_secret(name) else "missing"
        except Exception:
            secrets[name] = "vault_unavailable"
    hermes = ROOT / settings.hermes_checkout if settings.hermes_checkout else None
    commit = None
    if hermes and (hermes / ".git").exists():
        result = subprocess.run(["git", "-C", str(hermes), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        commit = result.stdout.strip() if result.returncode == 0 else None
    return {"phase": 4, "phase_status": "implementation_review", "python": sys.version.split()[0],
            "dependencies": dependencies, "secrets": secrets,
            "llm": {"provider": settings.llm_provider, "model": settings.llm_model, "connection": "not_probed"},
            "langsmith": {"region": settings.langsmith_region, "project": settings.langsmith_project, "connection": "not_probed"},
            "hermes": {"product": settings.hermes_product, "checkout_commit": commit,
                       "runtime_installed": bool(hermes and (hermes / ".venv/Scripts/hermes.exe").exists()),
                       "gateway_connection": "not_probed"},
            "gmail": {"connection": "not_probed", "setup_scope": "gmail.readonly", "writes_enabled": False},
            "frontend": "approved_layout_with_api_runtime", "business_harness": "supervised_langgraph_implemented"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Local integration and supervised runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Local inventory only; no remote requests")
    sub.add_parser("smoke", help="Synthetic offline LangGraph/SQLite compatibility check")
    sub.add_parser("vault-probe", help="Roundtrip a random synthetic value then delete it")
    sub.add_parser("hermes-probe", help="Start temporary loopback Gateway, check health/auth, then stop")
    serve = sub.add_parser("serve", help="Start the authenticated local runtime console")
    serve.add_argument("--open", action="store_true", dest="open_browser")
    serve.add_argument("--gateway",action="store_true",help="Also run the restricted local Hermes command gateway")
    corpus=sub.add_parser("dataset-import",help="Lock a local synthetic JSON evaluation corpus; no inference")
    corpus.add_argument("path",type=Path)
    evaluation=sub.add_parser("evaluate",help="Run versioned graph + independent evaluator")
    evaluation.add_argument("--dataset",default=None)
    evaluation.add_argument("--allow-network",action="store_true",required=True,help="Paid model inference and LangSmith metadata export")
    for command in ("run-fixture","diagnose","trace-flush"):
        explicit=sub.add_parser(command,help="Explicit local runtime check; real mail excluded")
        explicit.add_argument("--allow-network",action="store_true",required=True)
    store = sub.add_parser("secret-set", help="Hidden terminal input; never pass the key as an argument")
    store.add_argument("name", choices=NAMES[:2])
    delete = sub.add_parser("secret-delete", help="Delete one stored local secret; does not revoke the remote key")
    delete.add_argument("name", choices=NAMES)
    probe = sub.add_parser("probe", help="One explicit remote integration test")
    probe.add_argument("target", choices=("openai", "langsmith", "gmail"))
    probe.add_argument("--allow-network", action="store_true", required=True,
                       help="OpenAI uses paid inference; LangSmith writes synthetic trace/feedback")
    oauth = sub.add_parser("gmail-auth", help="Interactive Google login for a TEST Gmail account; readonly only")
    oauth.add_argument("--client-config", type=Path, required=True)
    oauth.add_argument("--test-account", action="store_true", required=True)
    oauth.add_argument("--draft-write",action="store_true",help="Explicitly request compose in addition to readonly")
    oauth.add_argument("--acknowledge-compose-includes-send",action="store_true",help="Acknowledge Google compose includes send; local broker still exposes Draft only")
    args = parser.parse_args()
    try:
        settings = load_settings()
        if args.command == "serve":
            from .app.launcher import serve
            serve(args.open_browser,args.gateway)
            return 0
        elif args.command in ("dataset-import","evaluate","run-fixture","diagnose","trace-flush"):
            from .app.launcher import local_service
            runtime=local_service()
            try:
                if args.command=="dataset-import":
                    from .app.datasets import import_dataset
                    result=import_dataset(runtime.store,args.path)
                elif args.command=="evaluate":
                    from .app.evaluation import evaluate
                    result=evaluate(runtime,args.dataset)
                elif args.command=="run-fixture":
                    result=runtime.start(wait=True)
                    job=runtime.store.get("job",result["id"])
                    result.update(status=job["status"],calls=job["calls"],active_ms=job.get("active_ms"),ledger_integrity=runtime.store.integrity(job["id"]))
                elif args.command=="diagnose":result=runtime.diagnose()
                else:result={"trace":runtime.telemetry.flush(limit=50),"experiments":runtime.telemetry.export_experiments()}
            finally:runtime.close()
        elif args.command == "doctor":
            result = doctor(settings)
        elif args.command == "smoke":
            from .smoke import offline_smoke
            result = offline_smoke()
        elif args.command == "hermes-probe":
            from .hermes_probe import hermes_probe
            result = hermes_probe(settings.hermes_checkout)
        elif args.command == "vault-probe":
            from uuid import uuid4
            from .secrets import vault, SERVICE
            backend = vault()
            name, value = "setup-probe-" + str(uuid4()), str(uuid4())
            try:
                backend.set_password(SERVICE, name, value)
                if backend.get_password(SERVICE, name) != value:
                    raise RuntimeError("Vault roundtrip mismatch")
            finally:
                backend.delete_password(SERVICE, name)
            result = {"status": "pass", "backend": "Windows Credential Manager", "synthetic_value_deleted": True}
        elif args.command == "secret-set":
            if not sys.stdin.isatty():
                raise ValueError("Run in your own interactive PowerShell terminal")
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass(f"{args.name} (hidden input): ")
            put_secret(args.name, value)
            value = ""
            result = {"status": "stored", "name": args.name, "storage": "Windows Credential Manager"}
        elif args.command == "secret-delete":
            delete_secret(args.name)
            result = {"status": "deleted_locally", "name": args.name, "remote_revocation": "not_performed"}
        elif args.command == "gmail-auth":
            from .probes import gmail_auth
            if args.draft_write and not args.acknowledge_compose_includes_send:raise ValueError("Compose acknowledgement required")
            result = gmail_auth(args.client_config,args.draft_write)
        else:
            from .probes import openai_probe, langsmith_probe, gmail_probe
            result = {"openai": lambda: openai_probe(settings),
                      "langsmith": lambda: langsmith_probe(settings),
                      "gmail": gmail_probe}[args.target]()
        report = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": args.command, **result}
        if args.command in ("doctor", "smoke", "vault-probe", "hermes-probe", "probe"):
            save_report(report, args.command, getattr(args, "target", ""))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Cancelled; no automatic retry.", file=sys.stderr)
        return 130
    except Exception as error:
        # SDK exceptions can contain request URLs, bodies, and credentials.
        report = {"checked_at": datetime.now(timezone.utc).isoformat(), "command": args.command,
                  **failure_report(error)}
        if args.command in ("doctor", "smoke", "vault-probe", "hermes-probe", "probe"):
            try:
                save_report(report, args.command, getattr(args, "target", ""))
            except OSError:
                report["report_saved"] = False
        print(json.dumps(report))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
