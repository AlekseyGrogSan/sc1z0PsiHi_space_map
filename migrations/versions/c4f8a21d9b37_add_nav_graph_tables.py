"""add nav_nodes and nav_edges tables (navigation graph)

Revision ID: c4f8a21d9b37
Revises: 6c466adabd65
Create Date: 2026-10-24 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8a21d9b37'
down_revision: Union[str, None] = '6c466adabd65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. nav_nodes — вершины навигационного графа на 2D-планах этажей
    op.create_table(
        'nav_nodes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('floor_id', sa.Uuid(), nullable=False),
        sa.Column('panorama_id', sa.Uuid(), nullable=True),
        sa.Column('x', sa.Float(), nullable=False),
        sa.Column('y', sa.Float(), nullable=False),
        sa.Column(
            'node_type',
            sa.String(length=32),
            nullable=False,
            server_default='walkway',
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "node_type IN ('walkway', 'door', 'stairs', 'elevator')",
            name='ck_nav_nodes_node_type',
        ),
        sa.ForeignKeyConstraint(['floor_id'], ['floors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['panorama_id'], ['panoramas.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_nav_nodes_floor_id'), 'nav_nodes', ['floor_id'], unique=False)
    op.create_index(op.f('ix_nav_nodes_panorama_id'), 'nav_nodes', ['panorama_id'], unique=False)

    # 2. nav_edges — рёбра графа: коридорные (в пределах этажа) и
    #    межэтажные (stairs/elevator) в одной таблице, различие — kind.
    op.create_table(
        'nav_edges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('from_node_id', sa.Uuid(), nullable=False),
        sa.Column('to_node_id', sa.Uuid(), nullable=False),
        sa.Column(
            'kind',
            sa.String(length=32),
            nullable=False,
            server_default='corridor',
        ),
        sa.Column('weight_meters', sa.Float(), nullable=False),
        sa.Column('is_accessible', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('bidirectional', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "kind IN ('corridor', 'stairs', 'elevator')",
            name='ck_nav_edges_kind',
        ),
        sa.ForeignKeyConstraint(['from_node_id'], ['nav_nodes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['to_node_id'], ['nav_nodes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_nav_edges_from_node_id'), 'nav_edges', ['from_node_id'], unique=False)
    op.create_index(op.f('ix_nav_edges_to_node_id'), 'nav_edges', ['to_node_id'], unique=False)
    op.create_index(op.f('ix_nav_edges_kind'), 'nav_edges', ['kind'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_nav_edges_kind'), table_name='nav_edges')
    op.drop_index(op.f('ix_nav_edges_to_node_id'), table_name='nav_edges')
    op.drop_index(op.f('ix_nav_edges_from_node_id'), table_name='nav_edges')
    op.drop_table('nav_edges')
    op.drop_index(op.f('ix_nav_nodes_panorama_id'), table_name='nav_nodes')
    op.drop_index(op.f('ix_nav_nodes_floor_id'), table_name='nav_nodes')
    op.drop_table('nav_nodes')
