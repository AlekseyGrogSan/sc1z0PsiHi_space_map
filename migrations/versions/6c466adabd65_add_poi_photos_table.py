"""add poi_photos table for POI photo gallery

Revision ID: 6c466adabd65
Revises: 0001_initial_core
Create Date: 2026-10-24 15:13:30.073980

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c466adabd65'
down_revision: Union[str, None] = '0001_initial_core'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'poi_photos',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('poi_id', sa.Uuid(), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['poi_id'], ['pois.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_poi_photos_poi_id'), 'poi_photos', ['poi_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_poi_photos_poi_id'), table_name='poi_photos')
    op.drop_table('poi_photos')