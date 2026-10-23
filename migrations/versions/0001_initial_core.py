"""initial core tables

Revision ID: 0001_initial_core
Revises: 
Create Date: 2026-10-23 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_initial_core'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('system_role', sa.String(length=50), nullable=False, server_default='organizer'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. spaces table
    op.create_table(
        'spaces',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('settings', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_spaces_slug'), 'spaces', ['slug'], unique=True)

    # 3. space_members table
    op.create_table(
        'space_members',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('space_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='viewer'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'user_id', name='uq_space_user'),
    )
    op.create_index(op.f('ix_space_members_space_id'), 'space_members', ['space_id'], unique=False)
    op.create_index(op.f('ix_space_members_user_id'), 'space_members', ['user_id'], unique=False)

    # 4. floors table
    op.create_table(
        'floors',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('space_id', sa.Uuid(), nullable=False),
        sa.Column('floor_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('plan_original_key', sa.String(length=500), nullable=True),
        sa.Column('plan_optimized_key', sa.String(length=500), nullable=True),
        sa.Column('plan_tiles_prefix', sa.String(length=500), nullable=True),
        sa.Column('width_px', sa.Integer(), nullable=True),
        sa.Column('height_px', sa.Integer(), nullable=True),
        sa.Column('ppm', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'floor_number', name='uq_space_floor_number'),
    )
    op.create_index(op.f('ix_floors_space_id'), 'floors', ['space_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_floors_space_id'), table_name='floors')
    op.drop_table('floors')
    op.drop_index(op.f('ix_space_members_user_id'), table_name='space_members')
    op.drop_index(op.f('ix_space_members_space_id'), table_name='space_members')
    op.drop_table('space_members')
    op.drop_index(op.f('ix_spaces_slug'), table_name='spaces')
    op.drop_table('spaces')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
