from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str | None = None
    inspect_timeout: float = 5.0
    inspect_cache_ttl: float = 3.0
    cors_origins: list[str] = ["*"]

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.celery_broker_url

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
