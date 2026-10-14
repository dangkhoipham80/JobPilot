"""where an employer's logo comes from, and the cached copy

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-14

Four nullable columns on ``companies``. ``logo_url`` is what a board said (the
JSON-LD ``hiringOrganization.logo``), ``domain`` is the employer's own site when
a source or the user knows it, ``logo_file`` is the downloaded copy served by
the dashboard, and ``logo_checked_at`` keeps a company with no findable logo
from being retried on every crawl. See ``jobpilot/companies/logos.py``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jobpilot"


def upgrade() -> None:
    op.add_column("companies", sa.Column("domain", sa.String(255), nullable=True), schema=SCHEMA)
    op.add_column("companies", sa.Column("logo_url", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("companies", sa.Column("logo_file", sa.String(64), nullable=True), schema=SCHEMA)
    op.add_column(
        "companies",
        sa.Column("logo_checked_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for col in ("logo_checked_at", "logo_file", "logo_url", "domain"):
        op.drop_column("companies", col, schema=SCHEMA)
