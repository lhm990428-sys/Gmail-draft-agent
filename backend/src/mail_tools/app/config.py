from pathlib import Path
import hashlib
import json
import tomllib
from pydantic import BaseModel, ConfigDict, Field
from mail_tools.settings import ROOT


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database_dir: Path = ROOT / ".local" / "application"
    llm_mode: str = Field(default="openai", pattern="^(openai|scripted)$")
    model: str = "gpt-5.4-mini-2026-03-17"
    allow_real_mail_export: bool = False
    allow_gmail_draft_write: bool = False
    trace_enabled: bool = True
    label: str = "agent-test"
    max_calls: int = Field(default=12, ge=1, le=12)
    max_output_tokens: int = Field(default=1200, ge=64, le=1600)
    token_budget: int = Field(default=20000, ge=1000, le=20000)
    active_timeout_seconds: int = Field(default=120, ge=5, le=120)
    daily_call_limit: int = Field(default=100, ge=1, le=500)
    session_seconds: int = Field(default=28800, ge=300, le=28800)
    artifact_days: int = Field(default=7, ge=1, le=7)
    automatic_mail: bool = False
    economy_profile: bool = False
    poll_seconds: int = Field(default=30,ge=15,le=300)
    auto_daily_messages: int = Field(default=100,ge=1,le=100)


def config() -> AppConfig:
    path = ROOT / "config" / "application.toml"
    return AppConfig.model_validate(tomllib.loads(path.read_text(encoding="utf-8-sig"))) if path.exists() else AppConfig()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
