"""Celery application. Redis is both broker and result backend."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "ai_project",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    broker_connection_retry_on_startup=True,
)

# Scheduled jobs (Celery beat). Add cron-style automations here — each entry
# points at a registered task. Run beat with `celery ... worker -B` (embedded,
# fine for a single worker) or a dedicated `celery ... beat` service at scale.
celery_app.conf.beat_schedule = {
    "sweep-stale-events": {
        "task": "app.sweep_stale_events",
        "schedule": float(settings.stale_sweep_interval_seconds),
    },
}

