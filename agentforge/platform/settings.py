"""AgentForge 平台代码：settings。

本模块定义平台运行配置，集中管理环境、数据库、鉴权、模型预算和外部连接参数，并通过环境变量覆盖默认值。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：Settings。
- 主要函数：get_settings。
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings。

    Settings 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - model_config: SettingsConfigDict(env_file='.env', env_prefix='AGENTFORGE_', extra='ignore')。
    - env: str。
    - database_url: str。
    - temporal_address: str。
    - temporal_namespace: str。
    - valkey_url: str。
    - object_store_endpoint: str。
    - vector_store: str。
    - otel_exporter_otlp_endpoint: str。
    - langfuse_host: str。
    - feishu_encrypt_key: str。
    - feishu_verification_token: str。
    - feishu_app_id: str。
    - feishu_app_secret: str。
    - feishu_signature_max_age_seconds: float。
    - events_im_webhook_secret: str。
    - auth_enabled: bool。
    - api_keys: dict[str, str]。
    - admin_api_key: str。
    - monthly_model_budget: float。
    - outbox_poll_interval_seconds: float。
    - kafka_bootstrap_servers: str。
    - kafka_topic: str。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

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
    # 飞书回调防重放时间窗口，单位为秒。设置为 0 表示关闭新鲜度检查，
    # 以兼容旧环境；生产环境建议配置为 300 秒等合理值，用于拒绝重复事件。
    # 该检查只影响飞书回调，不会替代签名验证和租户鉴权。
    feishu_signature_max_age_seconds: float = 0.0
    # 通用 IM Webhook `/v1/events/im` 的 HMAC 共享密钥。
    # 为空时跳过 HMAC 校验，但租户 API Key 鉴权仍然生效。
    events_im_webhook_secret: str = ""
    # P0-1 安全默认值反转：默认“要求鉴权”。实际是否生效由 create_platform_app
    # 的 fail-closed 推导决定——生产未配 key 拒启，非生产未配 key 降级并 WARNING。
    auth_enabled: bool = True
    api_keys: dict[str, str] = Field(default_factory=dict)
    admin_api_key: str = ""
    monthly_model_budget: float = 100.0
    outbox_poll_interval_seconds: float = 1.0
    kafka_bootstrap_servers: str = ""
    kafka_topic: str = "agentforge.domain-events"


@lru_cache
def get_settings() -> Settings:
    """读取并返回指定数据，并返回调用方需要的结果。

    Returns:
        Settings，函数执行后的结果。
    """
    return Settings()
