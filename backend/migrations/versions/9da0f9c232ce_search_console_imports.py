"""Add zero-cost manual GSC imports.

Revision ID: 9da0f9c232ce
Revises: c293d1f50ab7
"""
import sqlalchemy as sa
from alembic import op
revision='9da0f9c232ce'
down_revision='c293d1f50ab7'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('search_performance_imports',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('website_id',sa.Uuid(),nullable=False),
        sa.Column('uploaded_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('row_count',sa.Integer(),nullable=False),
        sa.Column('total_clicks',sa.Integer(),nullable=False),
        sa.Column('total_impressions',sa.Integer(),nullable=False),
        sa.Column('data',sa.JSON(),nullable=False),
        sa.ForeignKeyConstraint(['website_id'],['websites.id'],ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_search_performance_imports_website_id','search_performance_imports',['website_id'])

def downgrade():
    op.drop_index('ix_search_performance_imports_website_id',table_name='search_performance_imports')
    op.drop_table('search_performance_imports')
