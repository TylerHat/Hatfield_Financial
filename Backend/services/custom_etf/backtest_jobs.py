"""In-memory background job tracker for long-running ETF backtests.

Simple by design — a process-local dict keyed by UUID, with no persistence.
Jobs are lost on server restart. That's fine for the current use case: the
frontend polls the GET endpoint and re-runs from scratch on failure.

If we ever need cross-restart durability or multi-worker support, swap this
out for Redis / Celery / RQ.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Auto-evict completed jobs older than this many seconds. Keeps the dict
# from growing unbounded if the frontend never polls.
_JOB_TTL_SECONDS = 30 * 60   # 30 min

_jobs: dict = {}
_lock = threading.Lock()


def create_job(spec: dict) -> str:
    """Create a new job and return its ID. `spec` is stored for reference
    (e.g. so the polling endpoint can show what's running)."""
    job_id = uuid.uuid4().hex
    with _lock:
        _evict_stale_locked()
        _jobs[job_id] = {
            'id': job_id,
            'spec': spec,
            'status': 'pending',
            'progress': 0,
            'message': 'Queued',
            'result': None,
            'error': None,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'started_at': None,
            'finished_at': None,
            '_touched': time.time(),
        }
    logger.info('Job %s created: %s', job_id, spec)
    return job_id


def update_job(job_id: str, **fields) -> None:
    """Patch fields on a job. No-op if the job has been evicted."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.update(fields)
        job['_touched'] = time.time()


def set_running(job_id: str) -> None:
    update_job(job_id, status='running',
               started_at=datetime.now(timezone.utc).isoformat())


def set_progress(job_id: str, pct: float, message: str = None) -> None:
    fields = {'progress': max(0.0, min(100.0, float(pct)))}
    if message is not None:
        fields['message'] = message
    update_job(job_id, **fields)


def set_done(job_id: str, result: dict) -> None:
    update_job(job_id, status='done', progress=100, message='Complete',
               result=result,
               finished_at=datetime.now(timezone.utc).isoformat())


def set_error(job_id: str, error: str) -> None:
    update_job(job_id, status='error', message=error, error=error,
               finished_at=datetime.now(timezone.utc).isoformat())


def get_job(job_id: str) -> dict | None:
    """Return a clean (no internal fields) snapshot of the job, or None."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return {k: v for k, v in job.items() if not k.startswith('_')}


def run_job_async(job_id: str, fn, *args, **kwargs) -> None:
    """Spawn a daemon thread that runs `fn(job_id, *args, **kwargs)` and
    captures exceptions into the job's error field."""
    def _wrapper():
        try:
            set_running(job_id)
            fn(job_id, *args, **kwargs)
        except Exception as e:
            logger.exception('Job %s crashed', job_id)
            set_error(job_id, str(e))

    t = threading.Thread(target=_wrapper, daemon=True, name=f'job-{job_id[:8]}')
    t.start()


def _evict_stale_locked():
    """Drop completed/errored jobs older than TTL. Caller holds _lock."""
    now = time.time()
    stale = [
        jid for jid, j in _jobs.items()
        if j['status'] in ('done', 'error') and (now - j['_touched']) > _JOB_TTL_SECONDS
    ]
    for jid in stale:
        del _jobs[jid]
    if stale:
        logger.info('Evicted %d stale backtest jobs', len(stale))
