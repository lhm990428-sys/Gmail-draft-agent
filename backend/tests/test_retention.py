from datetime import datetime, timezone, timedelta
import secrets
from cryptography.fernet import Fernet
from mail_tools.app.config import AppConfig
from mail_tools.app.service import Service


def test_sensitive_expiry_preserves_ledger_hashes(tmp_path):
    service=Service(AppConfig(database_dir=tmp_path,llm_mode="scripted",trace_enabled=False),Fernet.generate_key(),secrets.token_bytes(32))
    try:
        rid=service.start(wait=True)["id"]
        job=service.store.get("job",rid)
        before=service.store.history(rid)
        from mail_tools.app.retention import expire_artifacts
        expire_artifacts(service,datetime.now(timezone.utc)+timedelta(days=8))
        assert service.store.get("mail",job["mailId"]) is None
        assert service.store.integrity(rid)
        assert not service.harness.state(rid).values
        assert all("input" not in event and "output" not in event and "memory" not in event for event in service.store.history(rid))
        assert service.store.get("job",rid)["artifactsExpired"] is True
    finally:service.close()
