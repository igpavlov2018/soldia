"""
Withdrawal API Schemas
"""

from decimal import Decimal
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class WithdrawalRequest(BaseModel):
    """Request to withdraw funds - requires Web3 signature"""
    wallet_address: str = Field(
        ...,
        min_length=32,
        max_length=64,
        description="User's Solana wallet address"
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        max_digits=10,
        decimal_places=2,
        description="Amount in USDC to withdraw"
    )
    destination_wallet: Optional[str] = Field(
        None,
        min_length=32,
        max_length=64,
        description="Destination wallet address (defaults to user wallet)"
    )
    signature: str = Field(
        ...,
        min_length=80,
        max_length=150,
        description="Base58-encoded signature from wallet owner"
    )
    message: Optional[str] = Field(
        None,
        description="Original message that was signed (for validation)"
    )


class WithdrawalResponse(BaseModel):
    """Response after withdrawal request"""
    success: bool
    withdrawal_id: Optional[int]
    amount: Decimal
    status: str
    message: str
    estimated_processing_time: Optional[str]


class WithdrawalStatusResponse(BaseModel):
    """Withdrawal status check"""
    withdrawal_id: int
    amount: Decimal
    status: str
    tx_hash: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
