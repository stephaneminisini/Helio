"""enforce a single row in systems

Revision ID: 003
Revises: 002
Create Date: 2026-08-12

The product is single-system (BRD 4.2). A check-then-insert in the API cannot
enforce that: two concurrent POST /api/settings requests with different
enphase_system_id values both pass the existence check and both commit. This
expression index admits exactly one row regardless of column values, so the
losing insert raises IntegrityError and the route maps it to 409.

"""
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index('uq_systems_singleton', 'systems', [sa.text('(true)')],
                    unique=True)


def downgrade() -> None:
    op.drop_index('uq_systems_singleton', table_name='systems')
