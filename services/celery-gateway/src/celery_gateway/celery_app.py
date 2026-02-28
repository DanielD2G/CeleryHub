from celery import Celery

from .config import settings

app = Celery("celeryhub-gateway")
app.config_from_object(
    {
        "broker_url": settings.celery_broker_url,
        "result_backend": settings.result_backend,
        "broker_connection_retry_on_startup": True,
    }
)
