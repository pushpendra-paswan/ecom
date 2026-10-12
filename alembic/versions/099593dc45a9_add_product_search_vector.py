"""add product search vector and newest-products index

Revision ID: 099593dc45a9
Revises: 6fc51572ed70
Create Date: 2026-10-12 04:48:11.996499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '099593dc45a9'
down_revision: Union[str, Sequence[str], None] = '6fc51572ed70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Checked by hand: a STORED generated column (Postgres keeps it up to date) and a GIN index on it.
    # The column is NOT NULL because name and description are NOT NULL.
    op.add_column('products', sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('english', name), 'A') || setweight(to_tsvector('english', description), 'B')", persisted=True), nullable=False))
    op.create_index('ix_products_search_vector', 'products', ['search_vector'], unique=False, postgresql_using='gin')
    # Partial index for the newest-first listing of active products (measured in PROJECT_CONTEXT.md)
    op.create_index('ix_products_active_newest', 'products', [sa.text('created_at DESC'), sa.text('id DESC')], unique=False, postgresql_where=sa.text('is_active IS TRUE'))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the indexes first, then the column
    op.drop_index('ix_products_active_newest', table_name='products', postgresql_where=sa.text('is_active IS TRUE'))
    op.drop_index('ix_products_search_vector', table_name='products', postgresql_using='gin')
    op.drop_column('products', 'search_vector')
