"""a job's last sighting, so the dedup window measures the right thing

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-17

The cross-source dedup window ("don't re-add a role another board already gave
me, if I saw it within N days") was filtered on ``crawled_at``. But
``crawled_at`` is the *first* sighting and is deliberately never bumped, so the
window counted down from the day a posting was discovered rather than from the
last time it was actually on a board. A job crawled every day for three weeks
was, on day fifteen, treated as long gone.

Hence a second timestamp rather than a redefinition of the first. The two answer
different questions and both are load-bearing: ``crawled_at`` feeds the
dashboard's by-day chart, the ``crawled`` sort and the ``crawled_after`` filter,
where "when did this arrive" is the whole point. Bumping *that* on re-crawl
would have been the cheaper migration and would have quietly moved every job
JobPilot has ever seen onto today's bar.

Backfilled from ``crawled_at``: for a row that predates this column, the last
time we can prove we saw it is the time we first did. That is an
under-statement, never an over-statement — the failure mode is one extra
cross-source row, not a suppressed one.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jobpilot"


def upgrade() -> None:
    # Nullable first, backfill, then NOT NULL. Adding it NOT NULL in one step
    # would fill existing rows with the server default (now()) and declare every
    # historical job as seen today — the exact error this column exists to stop.
    op.add_column(
        "jobs",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.execute(f"UPDATE {SCHEMA}.jobs SET last_seen_at = crawled_at WHERE last_seen_at IS NULL")
    op.alter_column(
        "jobs",
        "last_seen_at",
        nullable=False,
        server_default=sa.func.now(),
        schema=SCHEMA,
    )
    op.create_index("ix_jobs_last_seen_at", "jobs", ["last_seen_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_jobs_last_seen_at", table_name="jobs", schema=SCHEMA)
    op.drop_column("jobs", "last_seen_at", schema=SCHEMA)
