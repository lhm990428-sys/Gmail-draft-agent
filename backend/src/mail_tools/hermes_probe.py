"""Short-lived loopback Gateway liveness/auth check, without provider credentials."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
from tempfile import TemporaryDirectory
import time

import httpx
from .settings import ROOT

EXPECTED_COMMIT = "bf0203a794a07aac3ff764972ab9087baa4e4f4e"


def hermes_probe(checkout: str) -> dict:
    source = (ROOT / checkout).resolve()
    if not source.is_relative_to((ROOT / ".local").resolve()):
        raise ValueError("Hermes test checkout must be inside project .local")
    actual = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    if actual != EXPECTED_COMMIT:
        raise ValueError("Unexpected Hermes commit")
    python = source / ".venv/Scripts/python.exe"
    if not python.exists():
        raise ValueError("Install Hermes first")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    local = (ROOT / ".local").resolve()
    local.mkdir(exist_ok=True)
    # Hermes can mark its home files read-only. Keep a non-secret temporary
    # fixture directory on Windows instead of risking cleanup masking results.
    with TemporaryDirectory(prefix="gateway-probe-", dir=local, delete=False) as directory:
        home = Path(directory)
        (home / "config.yaml").write_text(
            "agent:\n  max_turns: 1\nplatform_toolsets:\n  cli: []\n  api_server: []\n"
            "approvals:\n  unattended_mode: deny\nplugins:\n  enabled: []\n", encoding="utf-8")
        # Explicit allowlist: no inherited provider, mail, or LangSmith secrets.
        env = {key: value for key, value in os.environ.items() if key.upper() in {
            "SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "USERPROFILE", "LOCALAPPDATA",
            "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "COMSPEC", "TEMP", "TMP",
        }}
        api_key = secrets.token_urlsafe(32)
        env.update(HERMES_HOME=str(home), PYTHONUTF8="1", HERMES_SAFE_MODE="1",
                   API_SERVER_ENABLED="true", API_SERVER_HOST="127.0.0.1",
                   API_SERVER_PORT=str(port), API_SERVER_KEY=api_key)
        with (home / "startup.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([str(python), "-m", "hermes_cli.main", "gateway", "run"],
                                       cwd=source, env=env, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                deadline = time.monotonic() + 80
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False) as client:
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError("Gateway exited before liveness; setup not connected")
                        try:
                            response = client.get("/health")
                            if response.status_code == 200 and response.json().get("status") == "ok":
                                break
                        except (httpx.HTTPError, ValueError):
                            pass
                        time.sleep(0.5)
                    else:
                        raise TimeoutError("Gateway liveness not confirmed within setup timeout")
                    denied = client.get("/v1/models")
                    allowed = client.get("/v1/models", headers={"Authorization": f"Bearer {api_key}"})
                    if denied.status_code not in (401, 403) or allowed.status_code != 200:
                        raise RuntimeError("Gateway auth boundary not verified")
                    return {"status": "pass", "product": "NousResearch/hermes-agent",
                            "commit": actual, "loopback_liveness": True,
                            "unauthenticated_models_status": denied.status_code,
                            "authenticated_models_status": allowed.status_code,
                            "provider_credentials_supplied": False,
                            "agent_runs_created": 0, "mail_access": False,
                            "application_adapter": "phase_4_not_built"}
            finally:
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       capture_output=True, timeout=10, check=False)
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
