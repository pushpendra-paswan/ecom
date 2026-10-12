"""add order list indexes (and replace the user_id index)

Revision ID: e918e5dbff2d
Revises: 408881ba845e
Create Date: 2026-10-12 06:25:10.903881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e918e5dbff2d'
down_revision: Union[str, Sequence[str], None] = '408881ba845e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The indexes were chosen by measuring (see "Performance review" in PROJECT_CONTEXT.md).
    # Postgres does not index foreign keys by itself: every order page loads its lines by order_id.
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'], unique=False)
    # The seller and admin order lists read the newest orders straight from this index instead of sorting them all
    op.create_index('ix_orders_created_at_id', 'orders', [sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False)
    # The customer's own list. user_id comes first, so it replaces the old index on user_id alone.
    op.create_index('ix_orders_user_id_created_at_id', 'orders', ['user_id', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False)
    op.drop_index('ix_orders_user_id', table_name='orders')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_index('ix_orders_user_id', 'orders', ['user_id'], unique=False)
    op.drop_index('ix_orders_user_id_created_at_id', table_name='orders')
    op.drop_index('ix_orders_created_at_id', table_name='orders')
    op.drop_index('ix_order_items_order_id', table_name='order_items')
