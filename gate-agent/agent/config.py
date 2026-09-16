from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    CENTRAL_API_URL: str = "http://127.0.0.1:8000/api/v1"
    GATE_CODE: str = "GATE-IN-01"
    GATE_API_KEY: str = "gate-dev-key"
    LOCAL_API_PORT: int = 8090
    HEARTBEAT_INTERVAL_SECONDS: int = 30
    SNAPSHOT_INTERVAL_SECONDS: int = 60
    LOG_LEVEL: str = "INFO"
    AGENT_VERSION: str = "1.0.0"
    DB_PATH: str = "agent.db"


@lru_cache
def get_settings() -> AgentSettings:
    return AgentSettings()


settings = get_settings()