"""add performance indexes

Revision ID: 002
Revises: 42deed428d85
Create Date: 2026-04-29

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
                    ['system_id', sa.text('interval_start DESC')])
    op.create_index('idx_daily_system_day', 'daily_summaries',
                    ['system_id', sa.text('day DESC')])
    op.create_index('idx_monthly_system_month', 'monthly_summaries',
                    ['system_id', sa.text('month DESC')])


def downgrade() -> None:
    op.drop_index('idx_monthly_system_month', table_name='monthly_summaries')
    op.drop_index('idx_daily_system_day', table_name='daily_summaries')
    op.drop_index('idx_intervals_system_start', table_name='energy_intervals')
