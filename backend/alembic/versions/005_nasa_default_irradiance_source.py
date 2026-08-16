"""default the irradiance source to nasa and drop nrel rows

Revision ID: 005
Revises: 004
Create Date: 2026-08-16

The NREL Solar Resource v1 endpoint only ever returned a long-term annual
average, which ingestion stored as though it were the day's measured value.
Weather normalisation is the whole point of the performance ratio, so every PR,
anomaly flag and degradation figure derived from an 'nrel' row is wrong. NASA
POWER supplies genuine daily values without a key, so it becomes the only
automatic source.

Existing 'nrel' irradiance rows are deleted rather than relabelled 'nasa': they
hold annual averages, and relabelling would launder bad data into the new source
name. Deleting leaves those days as gaps a later backfill can refill with real
daily values. It also avoids colliding with the (system_id, day, source) unique
constraint where a 'nasa' row already exists for the same day.

Systems still configured for 'nrel' are moved to 'nasa' so polling keeps working
without an operator editing the database.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("DELETE FROM irradiance WHERE source = 'nrel'")
    op.execute("UPDATE systems SET irradiance_source = 'nasa' "
               "WHERE irradiance_source = 'nrel'")
    op.alter_column('systems', 'irradiance_source',
                    existing_type=sa.String(length=32),
                    existing_nullable=False,
                    server_default='nasa')


def downgrade() -> None:
    # The deleted rows are not restored: they were annual averages, and the
    # backfill can refetch real daily values for those days.
    op.alter_column('systems', 'irradiance_source',
                    existing_type=sa.String(length=32),
                    existing_nullable=False,
                    server_default='nrel')
