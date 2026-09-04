"""companies and their HR contacts, and a job's link to one

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-05

Two tables and one column. The column is the interesting part: ``jobs`` already
carries a free-text ``company``, and this adds ``company_id`` *beside* it rather
than replacing it. The string is what the board printed and stays the evidence;
the link is a fold's opinion about which employer that string names, and an
opinion that can be re-derived must never be the only copy of a fact that
cannot.

The link is backfilled here rather than left to ``jobpilot backfill``. A
migration that creates the tables and stops leaves /companies empty and every
job unlinked until somebody remembers a second command — and an empty page is
indistinguishable from a broken one. ``companies.link_all_jobs`` is the same
function the CLI and the write paths use, so re-running the CLI afterwards is a
no-op rather than a second, differently-shaped answer.

That import is the one compromise: this file reaches into application code, so a
later rename of ``jobs.company`` or ``companies.normalized_name`` would break a
from-scratch upgrade at this revision. Accepted deliberately over freezing a
copy of the fold, because a frozen copy drifts from the live one silently and
the failure here is loud.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "jobpilot"


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("normalized_name", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )
    # Unique, not merely indexed: this key *is* company identity. A duplicate
    # would be two rows for one employer, each with half the HR contacts, and
    # nothing on screen would say which half you were looking at.
    op.create_index(
        "ix_companies_normalized_name",
        "companies",
        ["normalized_name"],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "hr_contacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], [f"{SCHEMA}.companies.id"], ondelete="CASCADE"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_hr_contacts_company_id", "hr_contacts", ["company_id"], schema=SCHEMA)

    op.add_column(
        "jobs",
        sa.Column("company_id", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    # SET NULL, not CASCADE: deleting a company unlinks its jobs, it does not
    # delete them. A cascade here would turn "I typed this employer's name wrong"
    # into "my corpus lost eleven postings".
    op.create_foreign_key(
        "fk_jobs_company_id",
        "jobs",
        "companies",
        ["company_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"], schema=SCHEMA)

    # Provision a company per distinct employer and link every existing job.
    # Imported inside the function so the module still imports on a checkout
    # where application code is broken — `alembic history` should not need the
    # app to load.
    from sqlalchemy.orm import Session

    from jobpilot.companies.service import link_all_jobs

    bind = op.get_bind()
    with Session(bind=bind) as session:
        result = link_all_jobs(session)
        session.commit()
    print(
        f"companies: created {result.created}, linked {result.linked} job(s)"
        + (f", {result.unlinkable} job(s) have no company name" if result.unlinkable else "")
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_company_id", table_name="jobs", schema=SCHEMA)
    op.drop_constraint("fk_jobs_company_id", "jobs", type_="foreignkey", schema=SCHEMA)
    op.drop_column("jobs", "company_id", schema=SCHEMA)
    op.drop_index("ix_hr_contacts_company_id", table_name="hr_contacts", schema=SCHEMA)
    op.drop_table("hr_contacts", schema=SCHEMA)
    op.drop_index("ix_companies_normalized_name", table_name="companies", schema=SCHEMA)
    op.drop_table("companies", schema=SCHEMA)
