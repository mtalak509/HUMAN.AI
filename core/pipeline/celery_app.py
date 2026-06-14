"""core.pipeline.celery_app — Celery application configuration.

Design decisions:
  D-03: NO result backend — the pipeline status lives exclusively on the Neo4j
        Document node (processing_status). Reading task state from Celery AsyncResult
        would create a competing source of truth. Do NOT add backend=... here.
  D-07: task_acks_late=True — task is only acknowledged after completion, so a
        worker crash during processing makes the task visible again (fair-restart).

Broker: Redis (Settings.redis_url), same Redis instance used by the API.
Tasks:  core.pipeline.tasks is included so Celery auto-discovers process_document.
"""

from celery import Celery

from core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "human_ai",
    broker=_settings.redis_url,
    # NO result backend by design (D-03): the pipeline status is the source of truth
    # on the Neo4j Document node (processing_status). Do NOT add backend=... — nothing
    # reads task return values, and a backend would invite reading status from AsyncResult,
    # which would erode D-03 (two competing sources of truth).
    include=["core.pipeline.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
