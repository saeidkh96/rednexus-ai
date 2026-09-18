from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/nexus-v1.db"
    manifest_path: str = "config/projects.json"
    redis_url: str = ""
    session_seconds: int = 3600
    approval_seconds: int = 3600
    lease_seconds: int = 120
    allowed_origins: tuple[str, ...] = ()
    allow_http: bool = False
    model_url: str = ""
    model_name: str = ""
    model_key_env: str = "NEXUS_MODEL_API_KEY"
    model_max_tokens: int = 2048

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.getenv("NEXUS_DATABASE_URL", cls.database_url),
            manifest_path=os.getenv("NEXUS_MANIFEST", cls.manifest_path),
            redis_url=os.getenv("NEXUS_REDIS_URL", ""),
            allowed_origins=tuple(filter(None, os.getenv("NEXUS_ALLOWED_ORIGINS", "").split(","))),
            allow_http=os.getenv("NEXUS_ALLOW_HTTP", "false").lower() == "true",
            model_url=os.getenv("NEXUS_MODEL_URL", ""),
            model_name=os.getenv("NEXUS_MODEL_NAME", ""),
        )

    def prepare(self):
        if self.database_url.startswith("sqlite:///"):
            filename = self.database_url.removeprefix("sqlite:///")
            if filename != ":memory:":
                Path(filename).parent.mkdir(parents=True, exist_ok=True)
