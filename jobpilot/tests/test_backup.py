"""Backups: the dump, the CV export, verification, retention and the mirror."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jobpilot import backup as backup_mod
from jobpilot.backup import BackupError, libpq_url, list_backups


def test_sqlalchemy_url_is_translated_for_pg_dump():
    """libpq rejects the +driver suffix with "invalid URI scheme", which reads
    like a malformed URL rather than a SQLAlchemy detail."""
    assert libpq_url("postgresql+psycopg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert libpq_url("postgresql+asyncpg://u:p@h/db") == "postgresql://u:p@h/db"
    # Already libpq-shaped: left alone.
    assert libpq_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def _touch(directory: Path, name: str, *, age_days: float = 0, size: int = 10) -> Path:
    p = directory / name
    p.write_bytes(b"x" * size)
    if age_days:
        old = (datetime.now(tz=timezone.utc) - timedelta(days=age_days)).timestamp()
        import os

        os.utime(p, (old, old))
    return p


def test_listing_is_newest_first_and_typed(tmp_path):
    _touch(tmp_path, "jobpilot-20260101-000000.dump", age_days=2)
    _touch(tmp_path, "cv-20260102-000000.json")
    files = list_backups(tmp_path)
    assert [f.kind for f in files] == ["cv", "database"]
    assert files[0].created > files[1].created


def test_listing_a_missing_directory_is_empty_not_an_error(tmp_path):
    """Before the first backup there is no directory; the page must still render."""
    assert list_backups(tmp_path / "nope") == []


def test_pruning_only_touches_files_this_module_wrote(tmp_path):
    """A glob wide enough to match something the user dropped in the folder is a
    glob that eventually deletes it."""
    _touch(tmp_path, "jobpilot-20260101-000000.dump", age_days=99)
    keep = _touch(tmp_path, "my-own-notes.txt", age_days=99)
    _touch(tmp_path, "cv-20260101-000000.json", age_days=1)

    removed = backup_mod._prune(tmp_path, keep_days=30)
    assert removed == ["jobpilot-20260101-000000.dump"]
    assert keep.exists(), "a file we did not write must never be pruned"
    assert (tmp_path / "cv-20260101-000000.json").exists()


def test_zero_retention_prunes_nothing(tmp_path):
    _touch(tmp_path, "jobpilot-20200101-000000.dump", age_days=9999)
    assert backup_mod._prune(tmp_path, keep_days=0) == []


def test_an_empty_dump_is_a_failure_not_a_success(tmp_path, monkeypatch):
    """The worst outcome is a job reporting success having written nothing --
    that is precisely what stops you checking."""
    monkeypatch.setattr(backup_mod, "find_pg_dump", lambda: "pg_dump")
    monkeypatch.setattr(
        backup_mod, "get_secrets",
        lambda: type("S", (), {"database_url": "postgresql://u:p@h/db"})(),
    )
    # pg_dump "succeeds" but writes nothing, the shape a full disk produces.
    monkeypatch.setattr(
        backup_mod.subprocess, "run",
        lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    with pytest.raises(BackupError, match="empty file"):
        backup_mod.run_backup(tmp_path)


def test_count_cap_prunes_even_when_nothing_is_old(tmp_path):
    """The hole age-only retention leaves: five presses of the dashboard button
    in one afternoon are ten files all inside the window, so nothing is ever
    removed and the directory grows without bound."""
    import os
    from datetime import datetime, timedelta, timezone

    for i in range(6):
        p = tmp_path / f"jobpilot-2026081{i}-000000.dump"
        p.write_bytes(b"x")
        when = (datetime.now(tz=timezone.utc) - timedelta(minutes=i)).timestamp()
        os.utime(p, (when, when))

    removed = backup_mod._prune(tmp_path, keep_days=30, keep_last=3)
    assert len(removed) == 3
    assert len(list(tmp_path.glob("jobpilot-*.dump"))) == 3
    # The three that survive are the newest three.
    assert "jobpilot-20260810-000000.dump" not in removed


def test_the_two_kinds_are_capped_independently(tmp_path):
    """A half-finished run leaves a dump with no CV beside it. Counting them
    together would let that orphan push a good CV out of the window."""
    for i in range(4):
        (tmp_path / f"jobpilot-2026081{i}-000000.dump").write_bytes(b"x")
    (tmp_path / "cv-20260810-000000.json").write_text("{}")

    backup_mod._prune(tmp_path, keep_days=0, keep_last=2)
    assert len(list(tmp_path.glob("cv-*.json"))) == 1, "the only CV must survive"
    assert len(list(tmp_path.glob("jobpilot-*.dump"))) == 2
