"""add panel_readings for per-microinverter daily production

Revision ID: 007
Revises: 006
Create Date: 2026-08-16

Per-panel monitoring (BR-15, BR-16) had nowhere to store data. Enphase reports
device-level telemetry as 5-minute intervals per microinverter; the poller sums
them into one row per panel per day, which is the grain the heatmap reads.

The unique constraint on (system_id, panel_serial, day) is what makes the poll
idempotent: re-polling a day updates the existing rows instead of duplicating
them. The (system_id, day) index serves the heatmap query, which asks for every
panel on a date range rather than for one panel over time.

energy_wh is nullable so a panel that reported no intervals can still be
recorded as present-but-silent rather than being omitted from the day.

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        'panel_readings',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('system_id', sa.Integer(), nullable=False),
        sa.Column('panel_serial', sa.String(length=64), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('energy_wh', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('system_id', 'panel_serial', 'day')
    )
    op.create_index('idx_panel_readings_system_day', 'panel_readings',
                    ['system_id', 'day'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_panel_readings_system_day', table_name='panel_readings')
    op.drop_table('panel_readings')
