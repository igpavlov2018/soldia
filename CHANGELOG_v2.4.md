# SOLDIA v2.4 — Bug Fix Release

## Исправленные недостатки из аудита v2.3

---

### 🔴 CRIT-3b: Admin key в URL — deposits.py (ИСПРАВЛЕНО)

**Файл:** `api/routes/deposits.py`

**Проблема:** Исправление CRIT-3 из v2.3 было применено только в `withdrawals.py`.
Эндпоинт `/deposits/pending` по-прежнему принимал `?admin_key=` как GET-параметр
и сравнивал его с `SECRET_KEY[:16]`.

**URL query-параметры логируются:** nginx access log, AWS CloudTrail, история браузера,
CDN логи, Sentry breadcrumbs. Это означало утечку части SECRET_KEY в логи.

**Исправление:**
- Удалён параметр `admin_key: str = ""` из сигнатуры функции
- Добавлен `x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")`
- Добавлена функция `_require_admin()` идентичная withdrawals.py
- Использует `settings.ADMIN_API_KEY` + `hmac.compare_digest`
- Лимитер переведён на `_real_ip` (X-Real-IP) — исправление CRIT-4b (см. ниже)

**Дополнительно:** Запрос `/pending` теперь использует один JOIN вместо N+1 отдельных
SELECT-запросов на каждую транзакцию, и добавлен `.limit(200)`.

---

### 🔴 CRIT-4b: IP-spoofing в rate limiting — deposits.py и users.py (ИСПРАВЛЕНО)

**Файлы:** `api/routes/deposits.py`, `api/routes/users.py`

**Проблема:** Лимитеры в этих роутерах использовали `get_remote_address` из slowapi,
которая читает `X-Forwarded-For[0]` — клиент-контролируемое значение.
Любой клиент мог обойти rate limiting, подставив произвольный IP в этот заголовок.
Регистрация (`5/hour`) и депозиты (`30/hour`) были полностью уязвимы.

Исправление CRIT-4 из v2.3 было применено только в `withdrawals.py` и `referrals.py`.

**Исправление:**
```python
# Было:
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

# Стало:
def _real_ip(request: Request) -> str:
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "0.0.0.0"

limiter = Limiter(key_func=_real_ip)
```

`X-Real-IP` устанавливается nginx из `$remote_addr` — клиент не может подделать.

---

### 🔴 NEW-1: Нет Alembic-миграции для idempotency_key (ИСПРАВЛЕНО)

**Файл:** `alembic/versions/003_v2_4_idempotency_and_pending_timeout.py`

**Проблема:** В v2.3 поле `Withdrawal.idempotency_key` было добавлено в ORM-модель,
но файл миграции создан не был. При деплое на существующую БД первый же вывод
падал с `ProgrammingError: column "idempotency_key" does not exist`.

**Исправление:** Создана миграция `003_v2_4_idempotency_and_pending_timeout`:
- `ALTER TABLE withdrawals ADD COLUMN idempotency_key VARCHAR(128)`
- Уникальный partial index: `UNIQUE WHERE idempotency_key IS NOT NULL`
  (не конфликтует со старыми NULL-записями без ключа)
- Partial index для быстрого поиска зависших pending-записей по таймауту

---

### 🟠 NEW-2: ADMIN_API_KEY не валидируется в production (ИСПРАВЛЕНО)

**Файл:** `config/settings.py`, `.env.example`

**Проблема:** `ADMIN_API_KEY` имел `default_factory=lambda: secrets.token_urlsafe(32)`.
При мультиворкерном деплое (Gunicorn с несколькими воркерами) каждый воркер
при старте генерировал свой случайный ключ. Admin-запрос проходил на одном воркере
и падал на другом — непредсказуемо.

**Исправление:**
- В `validate_configuration()` добавлена проверка: если `ENVIRONMENT=production`
  и `ADMIN_API_KEY` не задан или короче 32 символов — приложение не запускается
- В `.env.example` добавлена секция `ADMIN API KEY` с инструкцией по генерации

---

### 🟠 SER-2b: float() → Decimal в users.py::get_detailed_stats (ИСПРАВЛЕНО)

**Файл:** `api/routes/users.py`

**Проблема:** Функция `get_detailed_stats` использовала `float(referral.deposit_amount)`
и умножала на литерал `0.30` / `0.20` / `0.10`. Float-арифметика накапливает
погрешности в финансовых расчётах. Исправление SER-2 из v2.3 было применено
только в `withdrawals.py`.

**Исправление:**
```python
# Было:
deposit_amount = float(referral.deposit_amount)
earnings = deposit_amount * 0.30

# Стало:
deposit_amount = Decimal(str(referral.deposit_amount))
earnings = deposit_amount * constants.REFERRAL_RATE_L1  # Decimal("0.30")
```

Результат возвращается как строка: `str(earnings.quantize(Decimal("0.01")))` —
без потери точности при JSON-сериализации.

---

### 🟠 NullPool TypeError: pool_size с NullPool (ИСПРАВЛЕНО)

**Файл:** `database/manager.py`

**Проблема:** При `ENVIRONMENT=testing` использовался `NullPool`, но `create_async_engine()`
вызывался с параметрами `pool_size`, `max_overflow`, `pool_timeout`. В SQLAlchemy 2.0+
это вызывает `ArgumentError: Invalid argument(s) 'pool_size'` т.к. NullPool
не принимает эти параметры.

**Исправление:** Параметры пула передаются только при `QueuePool`:
```python
if settings.ENVIRONMENT == "testing":
    engine = create_async_engine(..., poolclass=NullPool)  # без pool_size
else:
    engine = create_async_engine(..., poolclass=QueuePool,
                                  pool_size=..., max_overflow=..., pool_timeout=...)
```

---

### 🟠 Celery задачи игнорировали AWS KMS (ИСПРАВЛЕНО)

**Файл:** `tasks/withdrawals.py`

**Проблема:** Celery-задачи вызывали `solana_client.send_usdc(private_key=settings.HOT_WALLET_PRIVATE_KEY)`.
При `USE_AWS_KMS=True` и незаданном `HOT_WALLET_PRIVATE_KEY` задача падала.
API-маршрут `withdrawals.py` использовал `solana_client.send_usdc()` без `private_key` —
клиент сам определял источник ключа. Celery-задачи так не делали.

**Исправление:** Убран явный аргумент `private_key` из вызовов `send_usdc()` в Celery.

---

### 🟠 NEW-4: Зависший PENDING блокирует повтор вывода (ИСПРАВЛЕНО)

**Файл:** `tasks/withdrawals.py`

**Проблема:** Если blockchain-запрос зависал без ответа (таймаут сети),
`Withdrawal.status` навсегда оставался `"pending"`. Клиент не мог повторить
вывод с тем же `idempotency_key` (409 Conflict) и не мог создать новый
(тот же кошелёк и сумма). Средства оставались зарезервированными.

**Исправление:** В `process_pending_withdrawals()` добавлена очистка зависших записей:
```python
PENDING_TIMEOUT_MINUTES = 30  # настраивается

# Перед обработкой активных pending — переводим старые в failed
stale = SELECT WHERE status='pending' AND created_at < now() - 30min
for wd in stale:
    RESTORE user.total_withdrawn -= wd.amount
    wd.status = 'failed'
    wd.error_message = "Timed out after 30 minutes in pending state"
```

После этого клиент может повторить вывод с новым `idempotency_key`.

---

## Матрица статусов всех исправлений

| # | Проблема | v2.3 | v2.4 |
|---|----------|------|------|
| CRIT-1 | Race condition SELECT FOR UPDATE | ✅ | ✅ |
| CRIT-2 | prev_last_withdrawal_at rollback | ✅ | ✅ |
| CRIT-3 | Admin key в URL (withdrawals) | ✅ | ✅ |
| CRIT-3b | Admin key в URL **(deposits)** | ❌ | ✅ |
| CRIT-4 | IP-spoofing (withdrawals/referrals) | ✅ | ✅ |
| CRIT-4b | IP-spoofing **(deposits/users)** | ❌ | ✅ |
| CRIT-5 | Redis GETDEL совместимость | ✅ | ✅ |
| SER-1 | Idempotency для вывода | ✅ | ✅ |
| SER-2 | float→Decimal (withdrawals) | ✅ | ✅ |
| SER-2b | float→Decimal **(users.py)** | ❌ | ✅ |
| SER-3 | N+1 в referrals | ✅ | ✅ |
| SER-4 | float в referrals → str | ✅ | ✅ |
| SER-5 | Redis KEYS → SCAN | ✅ | ✅ |
| NEW-1 | Нет миграции для idempotency_key | ❌ | ✅ |
| NEW-2 | ADMIN_API_KEY не валидируется в prod | ❌ | ✅ |
| NEW-3 | NullPool + pool_size TypeError | ❌ | ✅ |
| NEW-4 | KMS игнорируется в Celery | ❌ | ✅ |
| NEW-5 | PENDING-статус блокирует повтор | ❌ | ✅ |
