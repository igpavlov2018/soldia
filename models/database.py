"""
✅ FIXED v2.2: Database Models
- Removed withdrawn_today and withdrawn_monthly (no daily/monthly limits)
- last_withdrawal_at kept — used to detect "first withdrawal" for 2x rule
- All other models unchanged
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime,
    ForeignKey, Text, Index, UniqueConstraint, CheckConstraint
)
# MID-6 FIX: DeclarativeBase from sqlalchemy.orm (declarative_base deprecated in SA 2.0)
from sqlalchemy.orm import relationship, Mapped, mapped_column, DeclarativeBase
from sqlalchemy.sql import func
# OBS-2 FIX: FetchedValue marks updated_at as server-managed.
# onupdate=func.now() is an ORM client-side mechanism that is NOT triggered
# by Core UPDATE statements (update(User).where(...).values(...)).
# All financial balance updates use Core UPDATE, so updated_at was never
# refreshed with onupdate=func.now().
# Solution: declare server_onupdate=FetchedValue() so SQLAlchemy knows the
# DB sets this column, and add a DB-level trigger (migration 005) that does
# SET updated_at = NOW() on every UPDATE. SQLAlchemy will then expire the
# column after Core UPDATEs so the next access fetches the fresh DB value.
from sqlalchemy.schema import FetchedValue

class Base(DeclarativeBase):
    pass


class User(Base):
    """User model with wallet and referral data"""

    __tablename__ = "users"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Wallet
    wallet_address: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
        comment="Solana wallet address"
    )

    # Optional Telegram
    telegram_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Referral
    referrer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    referral_code: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, index=True,
        comment="Unique referral code for sharing"
    )

    # Deposit — set ONCE, never changed
    deposit_level: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="bronze/silver/gold/diamond — set once at first deposit"
    )
    deposit_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    deposit_tx_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True,
        comment="Solana transaction signature of deposit"
    )

    # Earnings
    total_earned: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    total_withdrawn: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )

    # Earnings breakdown by referral level
    earned_l1: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
        comment="Earnings from level 1 referrals"
    )
    earned_l2: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
        comment="Earnings from level 2 referrals"
    )
    earned_l3: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False,
        comment="Earnings from level 3 referrals"
    )

    # Status
    withdrawal_threshold_met: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Has user earned 2x their deposit? (flag, only meaningful before first withdrawal)"
    )
    last_withdrawal_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp of last withdrawal. NULL = no withdrawal yet (2x rule applies)"
    )
    # ✅ REMOVED: withdrawn_today, withdrawn_monthly — no daily/monthly limits
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    first_deposit_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        server_onupdate=FetchedValue(), nullable=False
        # OBS-2 FIX: server_onupdate=FetchedValue() instead of onupdate=func.now().
        # The actual UPDATE trigger is created in migration 005.
    )

    # Relationships
    referrer: Mapped[Optional["User"]] = relationship(
        "User", remote_side=[id], back_populates="referrals",
        foreign_keys=[referrer_id]
    )
    referrals: Mapped[List["User"]] = relationship(
        "User", back_populates="referrer", foreign_keys=[referrer_id]
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="user", foreign_keys="Transaction.user_id"
    )
    withdrawals: Mapped[List["Withdrawal"]] = relationship(
        "Withdrawal", back_populates="user", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("deposit_amount >= 0", name="check_deposit_amount_positive"),
        CheckConstraint("total_earned >= 0", name="check_total_earned_positive"),
        CheckConstraint("total_withdrawn >= 0", name="check_total_withdrawn_positive"),
        CheckConstraint("total_withdrawn <= total_earned", name="check_withdrawn_le_earned"),
        CheckConstraint("earned_l1 >= 0", name="check_earned_l1_positive"),
        CheckConstraint("earned_l2 >= 0", name="check_earned_l2_positive"),
        CheckConstraint("earned_l3 >= 0", name="check_earned_l3_positive"),
        Index("idx_user_referral_lookup", "referral_code", "is_active"),
        Index("idx_user_earnings", "total_earned", "withdrawal_threshold_met"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, wallet={self.wallet_address[:8]}...)>"


class Transaction(Base):
    """Transaction model for all financial operations"""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="deposit/referral_l1/referral_l2/referral_l3/withdrawal"
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    level: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Deposit level: bronze/silver/gold/diamond"
    )
    from_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="User who triggered this transaction (for referrals)"
    )
    tx_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True, unique=True,
        comment="Solana transaction signature"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
        comment="pending/completed/failed/cancelled"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions", foreign_keys=[user_id])
    from_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[from_user_id])

    __table_args__ = (
        CheckConstraint("amount > 0", name="check_transaction_amount_positive"),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'cancelled')",
            name="check_transaction_status_valid"
        ),
        Index("idx_transaction_user_type", "user_id", "type", "status"),
        Index("idx_transaction_created", "created_at", postgresql_using="brin"),
    )

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, type={self.type}, amount={self.amount})>"


class Withdrawal(Base):
    """Withdrawal request model"""

    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SER-1: idempotency key — client-supplied unique token per withdrawal attempt
    # Prevents duplicate processing if client retries on network error
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True, index=True,
        comment="Client-supplied idempotency key — unique per withdrawal attempt"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    wallet_address: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Destination wallet address"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
        comment="pending/processing/completed/failed/cancelled"
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tx_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True, unique=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        server_onupdate=FetchedValue(), nullable=False
        # OBS-2 FIX: see User.updated_at comment above.
    )

    user: Mapped["User"] = relationship("User", back_populates="withdrawals")

    __table_args__ = (
        CheckConstraint("amount > 0", name="check_withdrawal_amount_positive"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name="check_withdrawal_status_valid"
        ),
        Index("idx_withdrawal_user_status", "user_id", "status"),
        Index("idx_withdrawal_created", "created_at", postgresql_using="brin"),
    )

    def __repr__(self) -> str:
        return f"<Withdrawal(id={self.id}, user_id={self.user_id}, amount={self.amount})>"


class ProcessedTransaction(Base):
    """Track processed blockchain transactions to prevent duplicates"""

    __tablename__ = "processed_transactions"

    tx_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    transaction_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("idx_processed_tx_date", "processed_at", postgresql_using="brin"),
    )

    def __repr__(self) -> str:
        return f"<ProcessedTransaction(tx_hash={self.tx_hash[:8]}...)>"


class AuditLog(Base):
    """Audit log for all security-sensitive operations"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="JSON-encoded details")
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("idx_audit_event_user", "event_type", "user_id"),
        Index("idx_audit_created", "created_at", postgresql_using="brin"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, event={self.event_type})>"
