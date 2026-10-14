"""point a re-listed posting's older copies at its newest one

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-14

A board that re-lists a posting under a new id after the dedup window has passed
gets a second row — correctly, since the new id is the live one — but the old
rows stayed on the Jobs list beside it. ``latest_id`` lets every copy keep its
row (it may be shortlisted or applied to) while the list shows only the newest.
See ``jobpilot/crawler/reposts.py``.

Schema only. The groups are computed by the application's own matching rule, so
existing rows are linked by ``jobpilot backfill`` rather than by SQL here — a
second, SQL-shaped copy of that rule would drift from the first.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jobpilot"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("latest_id", sa.String(128), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        "fk_jobs_latest_id",
        "jobs",
        "jobs",
        ["latest_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_latest_id", "jobs", ["latest_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_jobs_latest_id", table_name="jobs", schema=SCHEMA)
    op.drop_constraint("fk_jobs_latest_id", "jobs", schema=SCHEMA, type_="foreignkey")
    op.drop_column("jobs", "latest_id", schema=SCHEMA)
