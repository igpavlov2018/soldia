"""
Deposit API Schemas
"""

from decimal import Decimal
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class DepositVerifyRequest(BaseModel):
    """Request to verify deposit transaction"""
    wallet_address: str = Field(..., min_length=32, max_length=64)
    tx_hash: str = Field(..., min_length=64, max_length=128)
    amount: Decimal = Field(..., gt=0)
    # CRIT-2 FIX: Ed25519 signature proving ownership of wallet_address.
    # Message signed by frontend: f"Deposit {tx_hash}"
    # Without this, anyone who knows a tx_hash can claim it for their own wallet.
    signature: str = Field(..., min_length=64, max_length=256,
                           description="Base58 Ed25519 signature of 'Deposit {tx_hash}'")


class DepositVerifyResponse(BaseModel):
    """Response after deposit verification"""
    success: bool
    verified: bool
    deposit_level: Optional[str]
    amount: Decimal
    referral_earnings: Optional[dict]
    message: str


class PendingDeposit(BaseModel):
    """Pending deposit info"""
    id: int
    wallet_address: str
    amount: Decimal
    tx_hash: str
    status: str
    created_at: datetime


class DepositListResponse(BaseModel):
    """List of pending deposits"""
    deposits: List[PendingDeposit]
    total_count: int
