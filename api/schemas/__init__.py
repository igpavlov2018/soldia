"""
API Schemas for request/response validation
"""

from .user import (
    UserRegisterRequest,
    UserRegisterResponse,
    UserStatsResponse,
    UserHistoryResponse
)
from .deposit import (
    DepositVerifyRequest,
    DepositVerifyResponse,
    DepositListResponse
)
from .withdrawal import (
    WithdrawalRequest,
    WithdrawalResponse,
    WithdrawalStatusResponse
)
from .referral import (
    ReferralTreeResponse,
    ReferralStatsResponse
)

__all__ = [
    # User
    "UserRegisterRequest",
    "UserRegisterResponse",
    "UserStatsResponse",
    "UserHistoryResponse",
    # Deposit
    "DepositVerifyRequest",
    "DepositVerifyResponse",
    "DepositListResponse",
    # Withdrawal
    "WithdrawalRequest",
    "WithdrawalResponse",
    "WithdrawalStatusResponse",
    # Referral
    "ReferralTreeResponse",
    "ReferralStatsResponse",
]
