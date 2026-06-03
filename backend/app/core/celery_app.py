from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# visibility_timeout DEVE ser maior que o maior countdown/ETA usado, senão o
# broker Redis reentrega a task (ETA > timeout) e ela executa em DUPLICIDADE.
# O auto-sync usa countdown=AUTO_SYNC_DELAY_SECONDS (padrão 3h) — damos folga (2x, mín. 24h).
_visibility_timeout = max(86400, settings.AUTO_SYNC_DELAY_SECONDS * 2)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_connection_timeout=10,
    broker_transport_options={"visibility_timeout": _visibility_timeout},
    result_backend_transport_options={"visibility_timeout": _visibility_timeout},
)

# Auto-discover
import app.services.tasks
