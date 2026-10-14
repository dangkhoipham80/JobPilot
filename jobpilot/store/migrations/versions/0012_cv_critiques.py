"""an advisory review of the Master CV against the crawled market

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-14

One row per critique run. Not a column on ``cv_versions``: a version is an
immutable record, and a critique is made after it, maybe several times for
different target roles. ``cv_version`` is a plain integer rather than a foreign
key because master versions are addressed by (scope, version), not by row id,
and a critique of version 17 stays true about version 17 whatever happens later.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jobpilot"


def upgrade() -> None:
    op.create_table(
        "cv_critiques",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cv_version", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(64), nullable=False, server_default=""),
        sa.Column("lang", sa.String(8), nullable=False, server_default="vi"),
        sa.Column("report", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("market", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("cv_critiques", schema=SCHEMA)
