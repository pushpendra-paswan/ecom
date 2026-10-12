"""payments refunded status and refund id

Revision ID: 408881ba845e
Revises: 099593dc45a9
Create Date: 2026-10-12 05:32:19.441876

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '408881ba845e'
down_revision: Union[str, Sequence[str], None] = '099593dc45a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Written by hand: autogenerate does not see CHECK constraint changes.
    # Replace the payments status CHECK (constraint name from the M1 migration) with one that also allows 'refunded'
    op.drop_constraint('ck_payments_status', 'payments', type_='check')
    op.create_check_constraint(
        'ck_payments_status', 'payments', "status IN ('pending', 'succeeded', 'failed', 'refunded')"
    )
    # The id of the Stripe refund (empty until a refund was made)
    op.add_column('payments', sa.Column('stripe_refund_id', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the new column first
    op.drop_column('payments', 'stripe_refund_id')
    # Rows that are 'refunded' would break the old CHECK, so they become 'succeeded' (the money was taken)
    op.execute("UPDATE payments SET status = 'succeeded' WHERE status = 'refunded'")
    # Put the old CHECK back
    op.drop_constraint('ck_payments_status', 'payments', type_='check')
    op.create_check_constraint('ck_payments_status', 'payments', "status IN ('pending', 'succeeded', 'failed')")
