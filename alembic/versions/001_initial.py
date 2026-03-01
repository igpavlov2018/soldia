"""Initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wallet_address', sa.String(length=64), nullable=False),
        sa.Column('telegram_id', sa.String(length=64), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('referrer_id', sa.Integer(), nullable=True),
        sa.Column('referral_code', sa.String(length=16), nullable=False),
        sa.Column('deposit_level', sa.String(length=20), nullable=True),
        sa.Column('deposit_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('deposit_tx_hash', sa.String(length=128), nullable=True),
        sa.Column('total_earned', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_withdrawn', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('earned_l1', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('earned_l2', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('earned_l3', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('withdrawal_threshold_met', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('first_deposit_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('deposit_amount >= 0', name='check_deposit_amount_positive'),
        sa.CheckConstraint('total_earned >= 0', name='check_total_earned_positive'),
        sa.CheckConstraint('total_withdrawn >= 0', name='check_total_withdrawn_positive'),
        sa.CheckConstraint('earned_l1 >= 0', name='check_earned_l1_positive'),
        sa.CheckConstraint('earned_l2 >= 0', name='check_earned_l2_positive'),
        sa.CheckConstraint('earned_l3 >= 0', name='check_earned_l3_positive'),
        sa.CheckConstraint('total_withdrawn <= total_earned', name='check_withdrawn_le_earned'),
        sa.ForeignKeyConstraint(['referrer_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wallet_address'),
        sa.UniqueConstraint('telegram_id'),
        sa.UniqueConstraint('referral_code')
    )
    op.create_index('idx_user_referral_lookup', 'users', ['referral_code', 'is_active'])
    op.create_index('idx_user_earnings', 'users', ['total_earned', 'withdrawal_threshold_met'])
    op.create_index(op.f('ix_users_is_active'), 'users', ['is_active'])
    op.create_index(op.f('ix_users_referral_code'), 'users', ['referral_code'])
    op.create_index(op.f('ix_users_referrer_id'), 'users', ['referrer_id'])
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'])
    op.create_index(op.f('ix_users_wallet_address'), 'users', ['wallet_address'])

    # Transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=True),
        sa.Column('from_user_id', sa.Integer(), nullable=True),
        sa.Column('tx_hash', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('amount > 0', name='check_transaction_amount_positive'),
        sa.CheckConstraint("status IN ('pending', 'completed', 'failed', 'cancelled')", name='check_transaction_status_valid'),
        sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tx_hash')
    )
    op.create_index('idx_transaction_user_type', 'transactions', ['user_id', 'type', 'status'])
    op.create_index('idx_transaction_created', 'transactions', ['created_at'], postgresql_using='brin')
    op.create_index(op.f('ix_transactions_created_at'), 'transactions', ['created_at'])
    op.create_index(op.f('ix_transactions_from_user_id'), 'transactions', ['from_user_id'])
    op.create_index(op.f('ix_transactions_status'), 'transactions', ['status'])
    op.create_index(op.f('ix_transactions_tx_hash'), 'transactions', ['tx_hash'])
    op.create_index(op.f('ix_transactions_type'), 'transactions', ['type'])
    op.create_index(op.f('ix_transactions_user_id'), 'transactions', ['user_id'])

    # Withdrawals table
    op.create_table(
        'withdrawals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('wallet_address', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('tx_hash', sa.String(length=128), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount > 0', name='check_withdrawal_amount_positive'),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')", name='check_withdrawal_status_valid'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tx_hash')
    )
    op.create_index('idx_withdrawal_user_status', 'withdrawals', ['user_id', 'status'])
    op.create_index('idx_withdrawal_created', 'withdrawals', ['created_at'], postgresql_using='brin')
    op.create_index(op.f('ix_withdrawals_created_at'), 'withdrawals', ['created_at'])
    op.create_index(op.f('ix_withdrawals_status'), 'withdrawals', ['status'])
    op.create_index(op.f('ix_withdrawals_tx_hash'), 'withdrawals', ['tx_hash'])
    op.create_index(op.f('ix_withdrawals_user_id'), 'withdrawals', ['user_id'])

    # Processed transactions table
    op.create_table(
        'processed_transactions',
        sa.Column('tx_hash', sa.String(length=128), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('transaction_type', sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('tx_hash')
    )
    op.create_index('idx_processed_tx_date', 'processed_transactions', ['processed_at'], postgresql_using='brin')

    # Audit logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_event_user', 'audit_logs', ['event_type', 'user_id'])
    op.create_index('idx_audit_created', 'audit_logs', ['created_at'], postgresql_using='brin')
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'])
    op.create_index(op.f('ix_audit_logs_event_type'), 'audit_logs', ['event_type'])
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'])


def downgrade():
    op.drop_table('audit_logs')
    op.drop_table('processed_transactions')
    op.drop_table('withdrawals')
    op.drop_table('transactions')
    op.drop_table('users')
