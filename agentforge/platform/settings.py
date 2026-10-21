"""配置模块。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """配置模型。

    Attributes:
        env: 环境。
        database_url: 数据库URL。
        temporal_address: Temporal。
        temporal_namespace: Temporal。
        valkey_url: ValkeyURL。
        object_store_endpoint: 对象存储端点。
        object_store_access_key: 对象存储访问键。
        object_store_secret_key: 对象存储密钥键。
        object_store_bucket: 对象存储存储桶。
        object_store_region: 对象存储。
        object_store_use_ssl: 对象存储。
        vector_store: 存储。
        otel_exporter_otlp_endpoint: 端点。
        langfuse_host: 字段值。
        feishu_encrypt_key: 飞书键。
        feishu_verification_token: 飞书核验令牌。
        feishu_app_id: 飞书应用ID。
        feishu_app_secret: 飞书应用密钥。
        feishu_signature_max_age_seconds: 飞书签名最大。
        events_im_webhook_secret: 事件Webhook密钥。
        auth_enabled: 鉴权启用。
        api_keys: API键。
        admin_api_key: 管理API键。
        monthly_model_budget: 月度模型预算。
        delivery_mode: 模式。
        saas_default_plan: 默认计划。
        saas_plans_json: 套餐JSON。
        enabled_modules: 启用模块。
        expense_category_limits: 报销。
        expense_monthly_budget_cents: 报销月度预算分。
        expense_invoice_enforcement: 报销发票。
        expense_invoice_block_alert_hours: 报销发票块告警。
        expense_invoice_override_alert_count: 报销发票覆盖告警数量。
        expense_invoice_alert_sweep_minutes: 报销发票告警扫描。
        attachment_download_ttl_seconds: 附件下载。
        support_default_sla_minutes: 客服默认SLA。
        support_sla_due_soon_seconds: 客服SLA到期。
        support_invoice_gate_team: 客服发票门禁。
        support_invoice_gate_assignee: 客服发票门禁。
        support_sla_sweep_minutes: 客服SLA扫描。
        support_sla_escalation_assignee: 客服SLA升级。
        support_notification_target: 客服通知目标。
        support_notification_webhook_url: 客服通知WebhookURL。
        support_notification_webhook_token: 客服通知Webhook令牌。
        support_notification_timeout_seconds: 客服通知超时。
        support_invoice_gate_sla_minutes: 客服发票门禁SLA。
        outbox_poll_interval_seconds: Outbox。
        kafka_bootstrap_servers: 启动装配。
        kafka_topic: 字段值。
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
    object_store_access_key: str = "agentforge"
    object_store_secret_key: str = "agentforge"
    object_store_bucket: str = "agentforge"
    object_store_region: str = "us-east-1"
    object_store_use_ssl: bool = False
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
    delivery_mode: str = "saas"
    saas_default_plan: str = "starter"
    saas_plans_json: str = ""
    # 逗号分隔的内置业务模块集合；
    # 私有化版本可以缩小该集合，而无需分叉应用或平台运行时代码。
    enabled_modules: str = "support,expense"
    expense_category_limits: str = ""
    expense_monthly_budget_cents: int = 0
    expense_invoice_enforcement: str = "off"
    expense_invoice_block_alert_hours: float = 24.0
    expense_invoice_override_alert_count: int = 5
    expense_invoice_alert_sweep_minutes: float = 15.0
    attachment_download_ttl_seconds: int = 300
    support_default_sla_minutes: int = 480
    support_sla_due_soon_seconds: int = 900
    support_invoice_gate_team: str = "finance-invoice-gate"
    support_invoice_gate_assignee: str = ""
    support_sla_sweep_minutes: float = 5.0
    support_sla_escalation_assignee: str = ""
    support_notification_target: str = ""
    support_notification_webhook_url: str = ""
    support_notification_webhook_token: str = ""
    support_notification_timeout_seconds: float = 10.0
    support_invoice_gate_sla_minutes: int = 60
    outbox_poll_interval_seconds: float = 1.0
    kafka_bootstrap_servers: str = ""
    kafka_topic: str = "agentforge.domain-events"

    @property
    def enabled_module_names(self) -> tuple[str, ...]:
        """返回启用模块名称。

        Returns:
            结果元组。
        """
        return tuple(
            dict.fromkeys(
                name.strip().lower() for name in self.enabled_modules.split(",") if name.strip()
            )
        )


@lru_cache
def get_settings() -> Settings:
    """读取配置。

    Returns:
        配置结果。
    """
    return Settings()
