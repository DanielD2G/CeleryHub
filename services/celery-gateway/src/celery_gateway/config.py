from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str | None = None
    inspect_timeout: float = 5.0
    inspect_cache_ttl: float = 3.0
    cors_origins: list[str] = []
    celeryhub_db_path: str = "./data/celeryhub.db"
    celeryhub_task_ttl: int = 604800
    celeryhub_auth_token: str = ""
    static_dir: str | None = None
    port: int = 3000

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.celery_broker_url

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
