from pathlib import Path
import os
import secrets
import shutil
import subprocess
import time
import httpx
from mail_tools.settings import ROOT, load_settings


class HermesGateway:
    """Owned foreground process; no service/cron/remote messenger registration."""
    def __init__(self,command_key):
        self.command_key=command_key;self.api_key=secrets.token_urlsafe(32);self.process=None;self.log=None
    def start(self):
        source=(ROOT/load_settings().hermes_checkout).resolve()
        if not source.is_relative_to((ROOT/".local").resolve()): raise ValueError("Unexpected Hermes checkout")
        home=ROOT/".local"/"runtime-gateway"
        plugin=home/"plugins"/"hermes-mail-runtime"
        plugin.mkdir(parents=True,exist_ok=True)
        for name in ("plugin.yaml","__init__.py"):
            shutil.copyfile(ROOT/"integrations/hermes-mail-runtime"/name,plugin/name)
        (home/"config.yaml").write_text("agent:\n  max_turns: 1\nplatform_toolsets:\n  cli: []\n  api_server: []\napprovals:\n  unattended_mode: deny\nplugins:\n  enabled:\n    - hermes-mail-runtime\n",encoding="utf-8")
        env={k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","PATH","PATHEXT","USERPROFILE","LOCALAPPDATA","APPDATA","COMSPEC","TEMP","TMP"}}
        env.update(HERMES_HOME=str(home),PYTHONUTF8="1",API_SERVER_ENABLED="true",API_SERVER_HOST="127.0.0.1",API_SERVER_PORT="8642",API_SERVER_KEY=self.api_key,HERMES_MAIL_COMMAND_KEY=self.command_key)
        # Fail if a different service owns this port; never reuse/kill it.
        import socket
        try:
            with socket.socket() as check: check.bind(("127.0.0.1",8642))
        except OSError as error:
            if error.errno in {48,98,10048} or getattr(error,"winerror",None)==10048:
                raise RuntimeError("HERMES_GATEWAY_PORT_IN_USE") from None
            raise
        self.log=(home/"gateway.log").open("w",encoding="utf-8")
        self.process=subprocess.Popen([str(source/".venv/Scripts/python.exe"),"-m","hermes_cli.main","gateway","run"],cwd=source,env=env,stdout=self.log,stderr=self.log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline=time.monotonic()+60
            with httpx.Client(timeout=2,trust_env=False) as client:
                while time.monotonic()<deadline:
                    if self.process.poll() is not None: raise RuntimeError("HERMES_GATEWAY_START_FAILED")
                    try:
                        if client.get("http://127.0.0.1:8642/health").status_code==200:return
                    except httpx.HTTPError: pass
                    time.sleep(.5)
            raise TimeoutError("HERMES_GATEWAY_START_TIMEOUT")
        except Exception:
            self.close();raise
    def command(self,text):
        with httpx.Client(timeout=30,trust_env=False) as client:
            response=client.post("http://127.0.0.1:8642/hermes-mail-runtime/command",headers={"Authorization":"Bearer "+self.api_key},json={"command":text})
            response.raise_for_status()
            return response.json()
    def close(self):
        if self.process and self.process.poll() is None:
            subprocess.run(["taskkill","/PID",str(self.process.pid),"/T","/F"],capture_output=True,timeout=10)
            self.process.wait(timeout=5)
        if self.log: self.log.close()
