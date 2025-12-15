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
    # Replay-protection window for Feishu callbacks (seconds). 0 disables the
    # freshness check to preserve backwards compatibility; set e.g. 300 in
    # production to reject replayed events.
    feishu_signature_max_age_seconds: float = 0.0
    # Shared secret for HMAC-signed generic IM webhooks (/v1/events/im).
    # Empty means HMAC is skipped (tenant auth still applies).
    events_im_webhook_secret: str = ""
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
