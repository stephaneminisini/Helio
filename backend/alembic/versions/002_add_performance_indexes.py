"""add performance indexes

Revision ID: 002
Revises: 42deed428d85
Create Date: 2026-04-29

Migration 001 was later amended to create these same three indexes, so on a
clean database they already exist by the time this revision runs and an
unconditional CREATE INDEX aborts `alembic upgrade head` with
DuplicateTableError. Databases that applied 001 before that amendment still
need them created here, so both paths are kept working by skipping indexes
that are already present. The definitions match 001 exactly, including the
DESC ordering. Dropping is left to 001 for the same reason.

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '42deed428d85'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index('idx_intervals_system_start', 'energy_intervals',
                    ['system_id', sa.text('interval_start DESC')],
                    if_not_exists=True)
    op.create_index('idx_daily_system_day', 'daily_summaries',
                    ['system_id', sa.text('day DESC')], if_not_exists=True)
    op.create_index('idx_monthly_system_month', 'monthly_summaries',
                    ['system_id', sa.text('month DESC')], if_not_exists=True)


def downgrade() -> None:
    pass
