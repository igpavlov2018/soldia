"""
services/referral.py — Referral earnings business logic.

АРХ-1 FIX: process_referral_earnings вынесена из api/routes/deposits.py
в отдельный сервисный модуль. Теперь её импортируют:
  - api/routes/deposits.py  (HTTP route layer)
  - tasks/deposits.py       (Celery task layer)

Это устраняет инверсию зависимостей: Celery task больше не импортирует
из HTTP route слоя.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, case, and_

from models.database import User, Transaction
from config.settings import constants

logger = logging.getLogger(__name__)


async def process_referral_earnings(
    user: User,
    deposit_amount: Decimal,
    session: AsyncSession
) -> dict:
    """
    АТОМАРНО: рассчитываем и зачисляем реферальные доходы в одной транзакции.

    Флаг withdrawal_threshold_met обновляется ТОЛЬКО если реферер ещё
    не сделал первый вывод (last_withdrawal_at IS NULL) — после первого
    вывода правило 2x больше не применяется.

    Args:
        user:           Пользователь чей депозит обрабатывается
        deposit_amount: Сумма депозита в USDC (Decimal)
        session:        Активная async сессия (вызывающий управляет транзакцией)

    Returns:
        dict с ключами 'l1', 'l2', 'l3' — суммы начисленных реферальных
        доходов в виде строк. Отсутствующий ключ = нет реферера на этом уровне.
    """
    earnings = {}

    # Уровень 1: прямой реферер
    if user.referrer_id:
        l1_earning = deposit_amount * constants.REFERRAL_RATE_L1

        stmt = (
            update(User)
            .where(User.id == user.referrer_id)
            .values(
                earned_l1=User.earned_l1 + l1_earning,
                total_earned=User.total_earned + l1_earning,
                withdrawal_threshold_met=case(
                    (and_(
                        User.last_withdrawal_at.is_(None),
                        User.deposit_amount > Decimal("0"),
                        User.total_earned + l1_earning >=
                            User.deposit_amount * Decimal(constants.WITHDRAWAL_MULTIPLIER)
                    ), True),
                    else_=User.withdrawal_threshold_met
                )
            )
            .returning(User)
        )

        # CRITICAL FIX: session.execute(update().returning(User)).scalar_one_or_none()
        # returns an int (the first column = id), NOT an ORM User object.
        # session.scalars() enables ORM-mode and correctly returns User instances.
        result = await session.scalars(stmt)
        l1_referrer = result.one_or_none()

        if l1_referrer:
            l1_tx = Transaction(
                user_id=l1_referrer.id,
                type=constants.TX_TYPE_REFERRAL_L1,
                amount=l1_earning,
                from_user_id=user.id,
                status=constants.STATUS_COMPLETED,
                completed_at=datetime.now(timezone.utc)
            )
            session.add(l1_tx)
            earnings['l1'] = str(l1_earning)

            logger.debug(
                f"✅ L1 Referral: User {user.id} -> Referrer {l1_referrer.id}: "
                f"{l1_earning} USDC"
            )

            # Уровень 2
            if l1_referrer.referrer_id:
                l2_earning = deposit_amount * constants.REFERRAL_RATE_L2

                stmt = (
                    update(User)
                    .where(User.id == l1_referrer.referrer_id)
                    .values(
                        earned_l2=User.earned_l2 + l2_earning,
                        total_earned=User.total_earned + l2_earning,
                        withdrawal_threshold_met=case(
                            (and_(
                                User.last_withdrawal_at.is_(None),
                                User.deposit_amount > Decimal("0"),
                                User.total_earned + l2_earning >=
                                    User.deposit_amount * Decimal(constants.WITHDRAWAL_MULTIPLIER)
                            ), True),
                            else_=User.withdrawal_threshold_met
                        )
                    )
                    .returning(User)
                )

                result = await session.scalars(stmt)
                l2_referrer = result.one_or_none()

                if l2_referrer:
                    l2_tx = Transaction(
                        user_id=l2_referrer.id,
                        type=constants.TX_TYPE_REFERRAL_L2,
                        amount=l2_earning,
                        from_user_id=user.id,
                        status=constants.STATUS_COMPLETED,
                        completed_at=datetime.now(timezone.utc)
                    )
                    session.add(l2_tx)
                    earnings['l2'] = str(l2_earning)

                    logger.debug(
                        f"✅ L2 Referral: User {user.id} -> Referrer {l2_referrer.id}: "
                        f"{l2_earning} USDC"
                    )

                    # Уровень 3
                    if l2_referrer.referrer_id:
                        l3_earning = deposit_amount * constants.REFERRAL_RATE_L3

                        stmt = (
                            update(User)
                            .where(User.id == l2_referrer.referrer_id)
                            .values(
                                earned_l3=User.earned_l3 + l3_earning,
                                total_earned=User.total_earned + l3_earning,
                                withdrawal_threshold_met=case(
                                    (and_(
                                        User.last_withdrawal_at.is_(None),
                                        User.deposit_amount > Decimal("0"),
                                        User.total_earned + l3_earning >=
                                            User.deposit_amount * Decimal(constants.WITHDRAWAL_MULTIPLIER)
                                    ), True),
                                    else_=User.withdrawal_threshold_met
                                )
                            )
                            .returning(User)
                        )

                        result = await session.scalars(stmt)
                        l3_referrer = result.one_or_none()

                        if l3_referrer:
                            l3_tx = Transaction(
                                user_id=l3_referrer.id,
                                type=constants.TX_TYPE_REFERRAL_L3,
                                amount=l3_earning,
                                from_user_id=user.id,
                                status=constants.STATUS_COMPLETED,
                                completed_at=datetime.now(timezone.utc)
                            )
                            session.add(l3_tx)
                            earnings['l3'] = str(l3_earning)

                            logger.debug(
                                f"✅ L3 Referral: User {user.id} -> Referrer {l3_referrer.id}: "
                                f"{l3_earning} USDC"
                            )

    return earnings
