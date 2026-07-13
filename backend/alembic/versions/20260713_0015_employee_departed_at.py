"""Add departed_at to employees for soft offboarding.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_employees_departed_at", "employees", ["departed_at"])


def downgrade() -> None:
    op.drop_index("ix_employees_departed_at", table_name="employees")
    op.drop_column("employees", "departed_at")
