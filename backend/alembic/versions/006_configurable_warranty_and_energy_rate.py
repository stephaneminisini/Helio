"""make the warranty threshold and energy rate configurable per system

Revision ID: 006
Revises: 005
Create Date: 2026-08-16

The warranty threshold was the module-level constant WARRANTY_THRESHOLD_PER_YEAR
in the efficiency route, so every install was measured against 0.7 percent per
year no matter what its modules are actually warranted for, and changing it
meant editing code and redeploying. The dollar value of lost production rested
on an unstated 0.15 per kWh default argument, which made the figure on the
Efficiency page uninterpretable.

Both become columns on systems. The defaults reproduce the previous hardcoded
values exactly, so an existing install upgrades with no change in behaviour and
no request fails: 0.700 percent per year and 0.1500 USD per kWh. NOT NULL is
safe because server_default backfills the existing row during the ALTER.

warranty_degradation_rate is a percent per year, matching the units of the
existing degradation_rate column rather than the fraction the route constant
used.

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('systems', sa.Column('warranty_degradation_rate',
                                       sa.Numeric(5, 3), nullable=False,
                                       server_default='0.700'))
    op.add_column('systems', sa.Column('energy_rate_per_kwh',
                                       sa.Numeric(8, 4), nullable=False,
                                       server_default='0.1500'))
    op.add_column('systems', sa.Column('energy_rate_currency',
                                       sa.String(length=3), nullable=False,
                                       server_default='USD'))


def downgrade() -> None:
    op.drop_column('systems', 'energy_rate_currency')
    op.drop_column('systems', 'energy_rate_per_kwh')
    op.drop_column('systems', 'warranty_degradation_rate')
