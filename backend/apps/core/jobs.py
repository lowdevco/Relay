"""
A deliberately small DB-backed job queue.

Webhooks persist data, call `enqueue()` inside their transaction and then
`dispatch()` the returned jobs after commit so the HTTP response is fast.

JOBS_MODE:
  thread  - run each dispatched job in a daemon thread (local development)
  worker  - leave jobs for `python manage.py run_jobs`
  sync    - run inline (tests)
"""

import logging
import threading
import traceback
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from .logging import redact
from .models import Job

logger = logging.getLogger(__name__)

_HANDLERS = {}


class RetryableJobError(Exception):
    """Raise from a handler to request a retry with backoff."""


def register(kind):
    def decorator(fn):
        _HANDLERS[kind] = fn
        return fn

    return decorator


def enqueue(kind, payload, *, workspace=None, dedupe_key=None, max_attempts=3, delay_seconds=0):
    """Create a job. Returns the Job, or None if `dedupe_key` was already used."""
    run_after = timezone.now() + timedelta(seconds=delay_seconds) if delay_seconds else None
    try:
        with transaction.atomic():
            return Job.objects.create(
                kind=kind,
                payload=payload,
                workspace=workspace,
                dedupe_key=dedupe_key,
                max_attempts=max_attempts,
                run_after=run_after,
            )
    except IntegrityError:
        return None


def dispatch(jobs):
    jobs = [j for j in jobs if j is not None]
    if not jobs:
        return
    mode = settings.JOBS_MODE
    if mode == "sync":
        for job in jobs:
            run_job(job.pk)
    elif mode == "thread":
        for job in jobs:
            threading.Thread(target=_thread_entry, args=(job.pk,), daemon=True).start()


def _thread_entry(job_id):
    close_old_connections()
    try:
        run_job(job_id)
    finally:
        close_old_connections()


def _claim(job_id):
    now = timezone.now()
    claimed = Job.objects.filter(pk=job_id, status=Job.Status.PENDING).update(
        status=Job.Status.RUNNING, updated_at=now
    )
    return claimed == 1


def run_job(job_id):
    if not _claim(job_id):
        return False
    job = Job.objects.get(pk=job_id)
    job.attempts += 1
    handler = _HANDLERS.get(job.kind)
    if handler is None:
        _ensure_handlers_loaded()
        handler = _HANDLERS.get(job.kind)
    try:
        if handler is None:
            raise RuntimeError(f"No handler registered for job kind '{job.kind}'")
        handler(**job.payload)
    except RetryableJobError as exc:
        _fail(job, exc, retry=job.attempts < job.max_attempts)
        return False
    except Exception as exc:  # noqa: BLE001 - jobs must never crash the worker
        logger.error("Job %s (%s) failed: %s", job.pk, job.kind, redact(traceback.format_exc()))
        _fail(job, exc, retry=False)
        return False
    job.status = Job.Status.DONE
    job.last_error = ""
    job.save(update_fields=["status", "attempts", "last_error", "updated_at"])
    return True


def _fail(job, exc, retry):
    job.last_error = redact(str(exc))[:2000]
    if retry:
        job.status = Job.Status.PENDING
        job.run_after = timezone.now() + timedelta(seconds=min(300, 5 * 3 ** (job.attempts - 1)))
    else:
        job.status = Job.Status.FAILED
    job.save(update_fields=["status", "attempts", "last_error", "run_after", "updated_at"])
    if retry and settings.JOBS_MODE == "thread":
        delay = (job.run_after - timezone.now()).total_seconds()
        timer = threading.Timer(max(1, delay), _thread_entry, args=(job.pk,))
        timer.daemon = True
        timer.start()


def due_jobs(limit=20):
    from django.db.models import Q

    now = timezone.now()
    return list(
        Job.objects.filter(status=Job.Status.PENDING)
        .filter(Q(run_after__isnull=True) | Q(run_after__lte=now))
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )


def requeue_stale(minutes=10):
    """Jobs stuck in RUNNING (e.g. the process died) go back to PENDING."""
    cutoff = timezone.now() - timedelta(minutes=minutes)
    return Job.objects.filter(status=Job.Status.RUNNING, updated_at__lt=cutoff).update(status=Job.Status.PENDING)


def _ensure_handlers_loaded():
    # Handlers live in tasks modules; importing registers them.
    import apps.automation.tasks  # noqa: F401
    import apps.whatsapp.tasks  # noqa: F401
