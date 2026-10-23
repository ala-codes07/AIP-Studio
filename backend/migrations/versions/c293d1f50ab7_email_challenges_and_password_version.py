"""Email verification, password recovery and token versioning.

Revision ID: c293d1f50ab7
Revises: bfd495d2165c
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = 'c293d1f50ab7'
down_revision = 'bfd495d2165c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_version', sa.Integer(), nullable=False, server_default='0'))
    # Existing users authenticated before email-OTP existed: grandfather them.
    # All NEW users are explicitly pending until their email is verified.
    op.execute('UPDATE users SET email_verified_at = CURRENT_TIMESTAMP')
    op.create_table('email_challenges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('purpose', sa.String(length=24), nullable=False),
        sa.Column('code_digest', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_challenges_user_id', 'email_challenges', ['user_id'])


def downgrade():
    op.drop_index('ix_email_challenges_user_id', table_name='email_challenges')
    op.drop_table('email_challenges')
    op.drop_column('users', 'password_version')
    op.drop_column('users', 'email_verified_at')
