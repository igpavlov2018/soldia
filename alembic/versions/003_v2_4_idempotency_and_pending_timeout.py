"""Add idempotency_key to withdrawals and pending timeout support

Revision ID: 003_v2_4_idempotency_and_pending_timeout
Revises: 002_security_enhancements
Create Date: 2026-02-21 00:00:00.000000

v2.4 FIXES:
  - Добавляет столбец idempotency_key в таблицу withdrawals
    (уникальный индекс — предотвращает двойную обработку)
  - created_at уже существует с индексом из 002, но нужен
    составной индекс (status, created_at) для эффективного
    поиска зависших pending-записей по таймауту
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_v2_4_idempotency_and_pending_timeout'
down_revision = '002_security_enhancements'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем idempotency_key в withdrawals
    # nullable=True для совместимости с существующими записями без ключа
    op.add_column('withdrawals', sa.Column(
        'idempotency_key',
        sa.String(128),
        nullable=True,
        comment="Client-supplied idempotency key — unique per withdrawal attempt"
    ))

    # Уникальный индекс на idempotency_key
    # WHERE idempotency_key IS NOT NULL — partial index, не мешает старым NULL-записям
    op.create_index(
        'idx_withdrawal_idempotency_key',
        'withdrawals',
        ['idempotency_key'],
        unique=True,
        postgresql_where=sa.text('idempotency_key IS NOT NULL')
    )

    # Составной индекс для поиска зависших pending-записей:
    # SELECT * FROM withdrawals WHERE status='pending' AND created_at < threshold
    # Уже есть idx_withdrawal_status_created из 002, проверяем и при необходимости создаём
    # (в 002 он был создан с postgresql_using='brin' — не оптимален для WHERE status=)
    # Добавляем btree-индекс для точных equality lookups по status
    op.create_index(
        'idx_withdrawal_pending_created',
        'withdrawals',
        ['created_at'],
        postgresql_where=sa.text("status = 'pending'")
    )


def downgrade():
    op.drop_index('idx_withdrawal_pending_created', table_name='withdrawals')
    op.drop_index('idx_withdrawal_idempotency_key', table_name='withdrawals')
    op.drop_column('withdrawals', 'idempotency_key')
