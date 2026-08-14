"""store rotated enphase tokens on the systems row

Revision ID: 004
Revises: 003
Create Date: 2026-08-14

Enphase rotates the refresh token on every use and the old one dies with the
call. Holding the rotated pair in memory only means every restart falls back to
the now-dead token in .env, so the install stops polling until an operator
pastes fresh tokens by hand. These columns hold the Fernet-encrypted pair plus
the rotation time, which drives the expiry warning.

Nullable so existing installs upgrade without a data migration: an empty column
falls back to the .env bootstrap values on the next poll, which then persists
what Enphase returns.

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('systems', sa.Column('enphase_access_token', sa.Text(),
                                       nullable=True))
    op.add_column('systems', sa.Column('enphase_refresh_token', sa.Text(),
                                       nullable=True))
    op.add_column('systems', sa.Column('token_updated_at',
                                       sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('systems', 'token_updated_at')
    op.drop_column('systems', 'enphase_refresh_token')
    op.drop_column('systems', 'enphase_access_token')
