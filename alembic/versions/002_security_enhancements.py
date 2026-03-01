"""Add withdrawal tracking and audit log enhancements

Revision ID: 002_security_enhancements
Revises: 001_initial
Create Date: 2026-02-16 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_security_enhancements'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # Add withdrawal tracking columns to users table
    op.add_column('users', sa.Column(
        'last_withdrawal_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last withdrawal"
    ))
    
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
    
    # Add constraint to ensure withdrawal amounts are positive
    op.create_check_constraint(
        'check_withdrawn_today_positive',
        'users',
        'withdrawn_today >= 0'
    )
    
    op.create_check_constraint(
        'check_withdrawn_monthly_positive',
        'users',
        'withdrawn_monthly >= 0'
    )
    
    # Add index for withdrawal tracking queries
    op.create_index(
        'idx_user_last_withdrawal',
        'users',
        ['last_withdrawal_at'],
        postgresql_using='brin'
    )
    
    # Enhance withdrawal table with additional tracking
    op.add_column('withdrawals', sa.Column(
        'retry_count',
        sa.Integer,
        server_default='0',
        nullable=False,
        comment="Number of retry attempts"
    ))
    
    # Create index for efficient withdrawal processing
    op.create_index(
        'idx_withdrawal_status_created',
        'withdrawals',
        ['status', 'created_at'],
        postgresql_using='brin'
    )


def downgrade():
    # Remove indexes
    op.drop_index('idx_withdrawal_status_created', table_name='withdrawals')
    op.drop_index('idx_user_last_withdrawal', table_name='users')
    
    # Remove constraints
    op.drop_constraint('check_withdrawn_monthly_positive', 'users')
    op.drop_constraint('check_withdrawn_today_positive', 'users')
    
    # Remove columns from withdrawals
    op.drop_column('withdrawals', 'retry_count')
    
    # Remove columns from users
    op.drop_column('users', 'withdrawn_monthly')
    op.drop_column('users', 'withdrawn_today')
    op.drop_column('users', 'last_withdrawal_at')
