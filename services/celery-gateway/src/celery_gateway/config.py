from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str | None = None
    inspect_timeout: float = 5.0
    inspect_cache_ttl: float = 3.0
    cors_origins: list[str] = []
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub"
    celeryhub_task_ttl: int = 604800
    celeryhub_auth_token: str = ""
    celeryhub_events_stream_maxlen: int = 1_000_000
    celeryhub_events_retention_days: int = 30
    # Alerting
    celeryhub_alerts_check_interval_s: float = 30.0
    celeryhub_alerts_cooldown_s: int = 1800
    celeryhub_alerts_http_timeout_s: float = 10.0
    celeryhub_persister_lag_threshold: int = 1000
    celeryhub_alert_events_retention_days: int = 90
    # Anomaly detection
    celeryhub_anomaly_runtime_factor: float = 3.0
    celeryhub_anomaly_consecutive_failures: int = 5
    static_dir: str | None = None
    port: int = 3000

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.celery_broker_url

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
