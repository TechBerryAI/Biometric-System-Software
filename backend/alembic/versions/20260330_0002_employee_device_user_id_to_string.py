"""Change employees.device_user_id from integer to string.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "employees",
        "device_user_id",
        existing_type=sa.Integer(),
        type_=sa.String(length=64),
        postgresql_using="device_user_id::text",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "employees",
        "device_user_id",
        existing_type=sa.String(length=64),
        type_=sa.Integer(),
        postgresql_using="NULLIF(regexp_replace(device_user_id, '[^0-9]', '', 'g'), '')::integer",
        existing_nullable=False,
    )
