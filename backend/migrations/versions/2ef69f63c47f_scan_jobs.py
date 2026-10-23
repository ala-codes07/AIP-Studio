"""Durable scan jobs.

Revision ID: 2ef69f63c47f
Revises: 9da0f9c232ce
"""
import sqlalchemy as sa
from alembic import op
revision='2ef69f63c47f'
down_revision='9da0f9c232ce'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('scan_jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('website_id',sa.Uuid(),nullable=False),
        sa.Column('status',sa.String(length=20),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('completed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('audit_id',sa.Uuid(),nullable=True),
        sa.Column('error',sa.Text(),nullable=False),
        sa.ForeignKeyConstraint(['website_id'],['websites.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['audit_id'],['website_audits.id'],ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_scan_jobs_website_id','scan_jobs',['website_id'])
    op.create_index('ix_scan_jobs_status','scan_jobs',['status'])

def downgrade():
    op.drop_index('ix_scan_jobs_status',table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_website_id',table_name='scan_jobs')
    op.drop_table('scan_jobs')
