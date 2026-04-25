from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


@contextmanager
def analyzer_job_lock(lock_path: Path, *, job_name: str):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError(f"{job_name} job already running; lock_path={lock_path}") from exc

    handle.seek(0)
    handle.truncate()
    handle.write(
        json.dumps(
            {
                "job_name": job_name,
                "pid": os.getpid(),
                "acquired_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    handle.flush()

    try:
        yield
    finally:
        try:
            handle.seek(0)
            handle.truncate()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
