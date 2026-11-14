from pathlib import Path
from typing import Literal
import tomllib

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config" / "local.toml"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Literal["dev"] = "dev"
    llm_provider: Literal["unconfigured", "openai"] = "unconfigured"
    llm_model: str = ""
    langsmith_region: Literal["unconfigured", "us", "eu"] = "unconfigured"
    langsmith_project: str = Field(default="hermes-mail-dev-setup", pattern=r"^hermes-mail-dev-[a-z0-9-]+$")
    langsmith_workspace_id: str = ""
    hermes_product: Literal["nousresearch/hermes-agent"] = "nousresearch/hermes-agent"
    hermes_checkout: str = ""

    @property
    def langsmith_endpoint(self) -> str:
        if self.langsmith_region == "unconfigured":
            raise ValueError("LangSmith region is not configured")
        return {"us": "https://api.smith.langchain.com", "eu": "https://eu.api.smith.langchain.com"}[self.langsmith_region]


def load_settings(path: Path = CONFIG) -> Settings:
    if not path.exists():
        return Settings()
    return Settings.model_validate(tomllib.loads(path.read_text(encoding="utf-8-sig")))
