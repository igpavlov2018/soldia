"""
✅ FIXED v2.5: User API Routes

ИСПРАВЛЕНИЯ v2.5:
  BUG-4: register_user теперь ловит IntegrityError при commit и возвращает
         HTTP 409 вместо HTTP 500 при гонке двух одновременных регистраций
         с одним wallet_address (оба прошли SELECT, второй падает на INSERT).

Без изменений от v2.4: CRIT-4 (X-Real-IP), SER-2 (Decimal stats).
"""

import logging
from decimal import Decimal

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from slowapi import Limiter

from database.manager import get_db_session
from models.database import User, Transaction
from api.schemas.user import (
    UserRegisterRequest,
    UserRegisterResponse,
    UserStatsResponse,
    UserHistoryResponse,
    TransactionHistoryItem
)
from security.auth import security_utils
from config.settings import constants

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== RATE LIMIT KEY: trusted IP from nginx ====================

def _real_ip(request: Request) -> str:
    """
    CRIT-4 FIX: Используем X-Real-IP (устанавливается nginx из $remote_addr).
    Клиент не может подделать этот заголовок.
    В nginx.conf должно быть: proxy_set_header X-Real-IP $remote_addr;
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "0.0.0.0"


limiter = Limiter(key_func=_real_ip)


# ==================== REGISTER ====================

@router.post("/register", response_model=UserRegisterResponse)
@limiter.limit(constants.RATE_LIMIT_REGISTER)
async def register_user(
    body: UserRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Регистрация нового пользователя

    - Создаёт аккаунт с адресом кошелька
    - Генерирует уникальный реферальный код
    - Привязывает к рефереру по коду, если указан
    """
    try:
        # Валидация адреса кошелька
        if not security_utils.is_valid_wallet_address(body.wallet_address):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Solana wallet address"
            )

        # Проверяем, не зарегистрирован ли пользователь
        result = await session.execute(
            select(User).where(User.wallet_address == body.wallet_address)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Wallet already registered"
            )

        # Ищем реферера по коду
        referrer_id = None
        if body.referral_code:
            result = await session.execute(
                select(User).where(User.referral_code == body.referral_code)
            )
            referrer = result.scalar_one_or_none()

            if not referrer:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Invalid referral code"
                )

            referrer_id = referrer.id

        # Генерируем уникальный реферальный код с ограничением попыток
        referral_code = security_utils.generate_referral_code()
        MAX_RETRIES = 10
        for attempt in range(MAX_RETRIES):
            result = await session.execute(
                select(User).where(User.referral_code == referral_code)
            )
            if not result.scalar_one_or_none():
                break
            referral_code = security_utils.generate_referral_code()
        else:
            logger.warning("Referral code collision detected, using longer code")
            referral_code = security_utils.generate_referral_code(length=12)

        # Создаём пользователя
        user = User(
            wallet_address=body.wallet_address,
            telegram_id=body.telegram_id,
            username=body.username,
            referrer_id=referrer_id,
            referral_code=referral_code
        )

        session.add(user)
        # BUG-4 FIX: Two concurrent requests with the same wallet_address can
        # both pass the SELECT check (both find nothing), then both attempt INSERT.
        # The second INSERT hits the UNIQUE constraint → IntegrityError.
        # Catching it here returns HTTP 409 instead of letting it bubble up as 500.
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Wallet already registered"
            )
        await session.refresh(user)

        logger.info(f"✅ User registered: {user.wallet_address}")

        return UserRegisterResponse(
            success=True,
            user_id=user.id,
            wallet_address=user.wallet_address,
            referral_code=user.referral_code,
            message="User registered successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


# ==================== STATS ====================

@router.get("/stats/{wallet_address}", response_model=UserStatsResponse)
@limiter.limit(constants.RATE_LIMIT_STATS)
async def get_user_stats(
    wallet_address: str,
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Статистика пользователя.

    MEDIUM-2 FIX: требует Ed25519-подпись кошелька в заголовке X-Signature.
    Frontend подписывает сообщение: f"Stats {wallet_address}"
    Без подписи любой мог запросить финансовые данные произвольного пользователя.
    """
    from security.web3_auth import verify_solana_signature
    if not x_signature or not await verify_solana_signature(
        f"Stats {wallet_address}", x_signature, wallet_address
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Signature header required (sign 'Stats {wallet_address}')."
        )
    try:
        result = await session.execute(
            select(User).where(User.wallet_address == wallet_address)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Подсчёт рефералов по уровням
        l1_result = await session.execute(
            select(func.count(User.id)).where(User.referrer_id == user.id)
        )
        referral_count_l1 = l1_result.scalar() or 0

        l2_result = await session.execute(
            select(func.count(User.id))
            .where(User.referrer_id.in_(
                select(User.id).where(User.referrer_id == user.id)
            ))
        )
        referral_count_l2 = l2_result.scalar() or 0

        l3_query = select(User.id).where(User.referrer_id.in_(
            select(User.id).where(User.referrer_id.in_(
                select(User.id).where(User.referrer_id == user.id)
            ))
        ))
        l3_result = await session.execute(select(func.count()).select_from(l3_query.subquery()))
        referral_count_l3 = l3_result.scalar() or 0

        return UserStatsResponse(
            wallet_address=user.wallet_address,
            deposit_level=user.deposit_level,
            deposit_amount=user.deposit_amount,
            total_earned=user.total_earned,
            total_withdrawn=user.total_withdrawn,
            earned_l1=user.earned_l1,
            earned_l2=user.earned_l2,
            earned_l3=user.earned_l3,
            withdrawal_threshold_met=user.withdrawal_threshold_met,
            referral_code=user.referral_code,
            referral_count_l1=referral_count_l1,
            referral_count_l2=referral_count_l2,
            referral_count_l3=referral_count_l3,
            created_at=user.created_at,
            first_deposit_at=user.first_deposit_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch stats"
        )


# ==================== DETAILED STATS ====================

@router.get("/stats/detailed/{wallet_address}")
@limiter.limit(constants.RATE_LIMIT_STATS)
async def get_detailed_stats(
    wallet_address: str,
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Детальная статистика рефералов по тирам и уровням.
    MEDIUM-2 FIX: требует X-Signature (sign 'Stats {wallet_address}').
    """
    from security.web3_auth import verify_solana_signature
    if not x_signature or not await verify_solana_signature(
        f"Stats {wallet_address}", x_signature, wallet_address
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Signature header required (sign 'Stats {wallet_address}')."
        )
    try:
        result = await session.execute(
            select(User).where(User.wallet_address == wallet_address)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Инициализируем структуру разбивки по тирам
        # SER-2: используем Decimal("0") вместо 0.0
        tiers = ['bronze', 'silver', 'gold', 'diamond']
        tiers_breakdown = {
            tier: {
                'l1': {'count': 0, 'earnings': Decimal("0")},
                'l2': {'count': 0, 'earnings': Decimal("0")},
                'l3': {'count': 0, 'earnings': Decimal("0")}
            }
            for tier in tiers
        }

        # L1 рефералы (прямые)
        l1_result = await session.execute(
            select(User).where(
                User.referrer_id == user.id,
                User.deposit_level.isnot(None)
            )
        )
        l1_referrals = l1_result.scalars().all()

        # Разбивка L1
        for referral in l1_referrals:
            tier = referral.deposit_level
            if tier in tiers_breakdown:
                # SER-2 FIX: Decimal(str(...)) — точное преобразование из Numeric
                deposit_amount = Decimal(str(referral.deposit_amount))
                earnings = deposit_amount * constants.REFERRAL_RATE_L1  # Decimal * Decimal

                tiers_breakdown[tier]['l1']['count'] += 1
                tiers_breakdown[tier]['l1']['earnings'] += earnings

        # L2 рефералы
        if l1_referrals:
            l1_ids = [r.id for r in l1_referrals]
            l2_result = await session.execute(
                select(User).where(
                    User.referrer_id.in_(l1_ids),
                    User.deposit_level.isnot(None)
                )
            )
            l2_referrals = l2_result.scalars().all()

            # Разбивка L2
            for referral in l2_referrals:
                tier = referral.deposit_level
                if tier in tiers_breakdown:
                    deposit_amount = Decimal(str(referral.deposit_amount))
                    earnings = deposit_amount * constants.REFERRAL_RATE_L2

                    tiers_breakdown[tier]['l2']['count'] += 1
                    tiers_breakdown[tier]['l2']['earnings'] += earnings

            # L3 рефералы
            if l2_referrals:
                l2_ids = [r.id for r in l2_referrals]
                l3_result = await session.execute(
                    select(User).where(
                        User.referrer_id.in_(l2_ids),
                        User.deposit_level.isnot(None)
                    )
                )
                l3_referrals = l3_result.scalars().all()

                # Разбивка L3
                for referral in l3_referrals:
                    tier = referral.deposit_level
                    if tier in tiers_breakdown:
                        deposit_amount = Decimal(str(referral.deposit_amount))
                        earnings = deposit_amount * constants.REFERRAL_RATE_L3

                        tiers_breakdown[tier]['l3']['count'] += 1
                        tiers_breakdown[tier]['l3']['earnings'] += earnings

        # SER-2: Конвертируем Decimal в строку для JSON (без потери точности)
        result_breakdown = {
            tier: {
                level: {
                    'count': data['count'],
                    'earnings': str(data['earnings'].quantize(Decimal("0.01")))
                }
                for level, data in levels.items()
            }
            for tier, levels in tiers_breakdown.items()
        }

        return {
            "success": True,
            "tiers_breakdown": result_breakdown
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Detailed stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch detailed stats"
        )


# ==================== HISTORY ====================

@router.get("/history/{wallet_address}", response_model=UserHistoryResponse)
@limiter.limit(constants.RATE_LIMIT_STATS)
async def get_user_history(
    wallet_address: str,
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session)
):
    """
    История транзакций пользователя.
    MEDIUM-2 FIX: требует X-Signature (sign 'Stats {wallet_address}').
    """
    from security.web3_auth import verify_solana_signature
    if not x_signature or not await verify_solana_signature(
        f"Stats {wallet_address}", x_signature, wallet_address
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Signature header required (sign 'Stats {wallet_address}')."
        )
    # Clamp limit/offset — no unbounded scans
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    try:
        result = await session.execute(
            select(User).where(User.wallet_address == wallet_address)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Получаем транзакции
        query = (
            select(Transaction)
            .where(Transaction.user_id == user.id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await session.execute(query)
        transactions = result.scalars().all()

        # Общее количество
        count_result = await session.execute(
            select(func.count(Transaction.id)).where(Transaction.user_id == user.id)
        )
        total_count = count_result.scalar() or 0

        transaction_items = [
            TransactionHistoryItem(
                id=tx.id,
                type=tx.type,
                amount=tx.amount,
                status=tx.status,
                tx_hash=tx.tx_hash,
                created_at=tx.created_at,
                completed_at=tx.completed_at
            )
            for tx in transactions
        ]

        return UserHistoryResponse(
            wallet_address=wallet_address,
            transactions=transaction_items,
            total_count=total_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"History error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch history"
        )
