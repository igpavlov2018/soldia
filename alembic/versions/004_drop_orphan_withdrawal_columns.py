"""Drop withdrawn_today and withdrawn_monthly — orphan columns added by 002

Revision ID: 004_drop_orphan_withdrawal_columns
Revises: 003_v2_4_idempotency_and_pending_timeout
Create Date: 2026-02-24 00:00:00.000000

BUG-3 FIX:
  Migration 002 added withdrawn_today and withdrawn_monthly to the users table.
  These columns were removed from models/database.py in v2.2 (no daily/monthly limits).
  Without this migration, the DB has ghost columns that:
    - alembic autogenerate will forever suggest to DROP
    - waste storage and confuse developers
  This migration drops them cleanly along with their CHECK constraints.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_drop_orphan_withdrawal_columns'
down_revision = '003_v2_4_idempotency_and_pending_timeout'
branch_labels = None
depends_on = None


def upgrade():
    # Drop CHECK constraints first (required before dropping columns in PostgreSQL)
    op.drop_constraint('check_withdrawn_today_positive', 'users', type_='check')
    op.drop_constraint('check_withdrawn_monthly_positive', 'users', type_='check')

    # Drop the orphan columns
    op.drop_column('users', 'withdrawn_today')
    op.drop_column('users', 'withdrawn_monthly')


def downgrade():
    # Restore columns (for rollback — data will be lost)
    op.add_column('users', sa.Column(
        'withdrawn_today',
        sa.Numeric(10, 2),
        server_default='0',
        nullable=False,
        comment="Amount withdrawn today (resets at midnight UTC)"
    ))
    op.add_column('users', sa.Column(
        'withdrawn_monthly',
        sa.Numeric(10, 2),
        server_default='0',
        nullable=False,
        comment="Amount withdrawn this month (resets on 1st)"
    ))
    op.create_check_constraint(
        'check_withdrawn_today_positive', 'users', 'withdrawn_today >= 0'
    )
    op.create_check_constraint(
        'check_withdrawn_monthly_positive', 'users', 'withdrawn_monthly >= 0'
    )
