from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings


celery_app = Celery(
    "transaction_pipeline",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.process_job"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Delete task results from Redis after 1 hour — prevents memory bloat
    result_expires=3600,
    # Don't pre-fetch more tasks than the worker can handle concurrently
    worker_prefetch_multiplier=1,
    # Only acknowledge the task AFTER it completes — prevents silent job loss on crash
    task_acks_late=True,
    # Visibility timeout must exceed the longest possible task runtime
    # (LLM calls can be 30s x 3 retries = 90s; set to 12h for safety)
    broker_transport_options={
        "visibility_timeout": 43200,
    },
)


@worker_process_init.connect
def on_worker_process_init(**kwargs: object) -> None:
    """Dispose inherited DB connections after Celery forks a new worker process.

    Without this, forked child processes share the parent's SQLAlchemy connection
    state, which can cause 'SSL error: decryption failed' or silent data corruption
    when multiple workers try to use the same underlying socket.
    """
    from app.core.database import engine

    engine.dispose()

