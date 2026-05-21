"""Add optional full_name to users for profile display.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=160), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "full_name")
