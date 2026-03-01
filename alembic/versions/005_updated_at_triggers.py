"""
005_updated_at_triggers

OBS-2 FIX: Add PostgreSQL triggers to keep updated_at current on every UPDATE.

Previously: onupdate=func.now() in SQLAlchemy models — this is an ORM
client-side mechanism. It only fires when SQLAlchemy ORM flushes changes
to a mapped object attribute. All financial balance changes in this codebase
use Core UPDATE statements (update(User).where(...).values(...)), which bypass
the ORM mapper entirely. As a result, updated_at was never actually updated
after the initial INSERT.

Fix: DB-level BEFORE UPDATE triggers so updated_at is always refreshed
regardless of whether the update came from ORM or Core, from Python or
from a DBA running SQL directly.

Revision ID: 005
Revises: 004
Create Date: 2025-xx-xx
"""

from alembic import op

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # Create shared trigger function (reused by both tables)
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Trigger for users table
    op.execute("""
        DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)

    # Trigger for withdrawals table
    op.execute("""
        DROP TRIGGER IF EXISTS trg_withdrawals_updated_at ON withdrawals;
        CREATE TRIGGER trg_withdrawals_updated_at
        BEFORE UPDATE ON withdrawals
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users;")
    op.execute("DROP TRIGGER IF EXISTS trg_withdrawals_updated_at ON withdrawals;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
