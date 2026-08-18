"""Backups: what exists, and a button to make another one.

Read-only plus one trigger. There is deliberately **no delete endpoint**: the
only automatic deletion is the retention pass inside the backup job itself,
which is bounded and predictable. A button that removes backups is a button that
removes the thing you kept for the day everything else went wrong, and the
dashboard is reachable from a phone.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from jobpilot.api.deps import require_token
from jobpilot.api.schemas import TaskOut
from jobpilot.backup import backup_body, list_backups, restore_hint
from jobpilot.config import get_config
from jobpilot.orchestrator import TaskBusy, queue

router = APIRouter(prefix="/backups", tags=["backups"], dependencies=[Depends(require_token)])

#: Sentinel for the queue's one-task-per-job guard. Backups are not tied to a
#: job, but two running at once would race on the same directory and the same
#: retention pass, so they borrow the mechanism that already exists.
BACKUP_LOCK = "__backup__"


@router.get("")
def read_backups() -> dict:
    """Everything in the backup directory, newest first, plus how to restore it."""
    cfg = get_config().backup
    directory = Path(cfg.dir).expanduser()
    files = list_backups(directory)

    return {
        "directory": str(directory),
        "exists": directory.is_dir(),
        "keep_days": cfg.keep_days,
        "remote": cfg.remote,
        "remote_keep_days": cfg.remote_keep_days,
        "total_bytes": sum(f.size for f in files),
        # A backup nobody knows how to restore is a backup nobody has, so the
        # command is shown next to the files. The password is masked.
        "restore_hint": restore_hint(directory),
        "items": [
            {
                "name": f.name,
                "size": f.size,
                "created_at": f.created.isoformat(),
                "kind": f.kind,
            }
            for f in files
        ],
    }


@router.post("", response_model=TaskOut, status_code=202)
def start_backup() -> JSONResponse:
    """Run a backup now. Answers with a task; progress arrives over the WebSocket.

    202 rather than a result: dumping the database and uploading it can take
    longer than a request should live, and doing it inline would hold a worker
    while the phone that started it has already locked its screen.
    """
    try:
        task = queue.submit(
            "backup",
            backup_body,
            label="Backing up database + CV",
            job_id=BACKUP_LOCK,
            exclusive=True,
        )
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(status_code=202, content=TaskOut(**task.to_dict()).model_dump(mode="json"))
