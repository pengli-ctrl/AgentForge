from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENTFORGE_",
        extra="ignore",
    )

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    valkey_url: str = "redis://localhost:6379/0"
    object_store_endpoint: str = "http://localhost:9000"
    vector_store: str = "pgvector"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    langfuse_host: str = "http://localhost:3000"
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    auth_enabled: bool = False
    api_keys: dict[str, str] = Field(default_factory=dict)
    admin_api_key: str = ""
    monthly_model_budget: float = 100.0
    outbox_poll_interval_seconds: float = 1.0
    kafka_bootstrap_servers: str = ""
    kafka_topic: str = "agentforge.domain-events"


@lru_cache
def get_settings() -> Settings:
    return Settings()
