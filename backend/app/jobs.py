"""Tiny background-job runner so long training runs do not block HTTP requests.

Only one job runs at a time (a lock), which keeps results reproducible and
avoids two runs writing models simultaneously. Job state is in memory; results
themselves are persisted in SQLite by the job function.
"""
from __future__ import annotations

import threading
import traceback
import uuid
from typing import Any, Callable

from . import db

_jobs: dict[str, dict[str, Any]] = {}
_run_lock = threading.Lock()


def submit(kind: str, fn: Callable[[Callable[[int, int, str], None]], Any]) -> dict:
    if _run_lock.locked():
        running = next((j for j in _jobs.values() if j["status"] == "running"), None)
        raise RuntimeError(f"Another job is already running ({running['kind'] if running else 'unknown'}). Wait for it to finish.")
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "kind": kind, "status": "queued", "progress": 0, "total": 0, "message": "", "result": None,
           "error": None, "created_at": db.now_iso()}
    _jobs[job_id] = job

    def progress(done: int, total: int, msg: str) -> None:
        job.update(progress=done, total=total, message=msg)

    def run() -> None:
        with _run_lock:
            job["status"] = "running"
            try:
                job["result"] = fn(progress)
                job["status"] = "finished"
            except Exception as exc:  # report the real error to the UI
                job["status"] = "failed"
                job["error"] = getattr(exc, "message", None) or str(exc)
                job["traceback"] = traceback.format_exc(limit=5)
            job["finished_at"] = db.now_iso()

    threading.Thread(target=run, daemon=True).start()
    return job


def get(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def is_running() -> bool:
    return _run_lock.locked()
