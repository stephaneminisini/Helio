"""let the expected PR baseline be configured per system

Revision ID: 008
Revises: 007
Create Date: 2026-08-18

Expected Performance Ratio was anchored at 1.0, which asserts that every watt of
irradiance landing on the array arrives as metered AC energy. Inverter
conversion, module temperature, soiling, wiring and mismatch losses put a healthy
system between 0.75 and 0.85, so the anchor was unreachable: every month was
flagged as an anomaly and lost production was overstated by the whole conversion
loss.

The baseline is now measured from the system's own first year of Performance
Ratio, and this column overrides that measurement for an owner who knows what
their install was commissioned at, or who wants figures before a year of history
exists.

Nullable with no default on purpose. There is no value that is right for every
install, and a default would be exactly the invented standard this replaces: a
null means "measure it", which is the honest position for a system whose own
output has not been observed yet. Stored as a fraction, matching
monthly_summaries.performance_ratio and expected_pr rather than the percent that
degradation_rate uses.

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('systems', sa.Column('baseline_pr',
                                       sa.Numeric(6, 4), nullable=True))


def downgrade() -> None:
    op.drop_column('systems', 'baseline_pr')
