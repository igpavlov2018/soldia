# SOLDIA v2.2 — CHANGELOG (Bug Fix Release)

## Исправленные баги

### 🔴 BUG-02 FIXED — `@celery.task` отсутствовал у `send_withdrawal`
**Файл:** `tasks/withdrawals.py`
Функция `send_withdrawal` не была декорирована как Celery-задача.
Вызов `.delay()` вызывал `AttributeError`. Исправлено.

### 🔴 BUG-03 FIXED — `send_usdc()` вызывался с несуществующим параметром `from_wallet`
**Файл:** `tasks/withdrawals.py`
`send_usdc(from_wallet=..., to_wallet=..., amount=..., private_key=...)` — параметр `from_wallet`
не существует в сигнатуре функции. Вызывал `TypeError`. Исправлено.

### 🔴 BUG-04 FIXED — Double-spend при сбое между отправкой и записью в БД
**Файл:** `api/routes/withdrawals.py`
Правильный порядок: сначала резервируем средства в БД (`total_withdrawn += amount`, статус `pending`),
затем отправляем на блокчейн. При ошибке блокчейна — откатываем `total_withdrawn -= amount`.

### 🔴 BUG-05 FIXED — Неверная логика лимитов вывода
**Файлы:** `api/routes/withdrawals.py`, `config/settings.py`, `models/database.py`, `tasks/withdrawals.py`
Удалены дневные/месячные лимиты и ограничения частоты вывода.
После разблокировки вывода пользователь может выводить без ограничений.
Удалены поля `withdrawn_today`, `withdrawn_monthly` из модели User.
Удалены Celery-задачи `reset_daily_limits` и `reset_monthly_limits`.

### 🔴 BUG-06 FIXED — Правило 2× работало всегда, а не только до первого вывода
**Файлы:** `api/routes/withdrawals.py`, `api/routes/deposits.py`
Правило 2× применяется ТОЛЬКО до первого вывода (`last_withdrawal_at IS NULL`).
После первого вывода пользователь выводит сколько угодно без порогов.
Флаг `withdrawal_threshold_met` тоже обновляется только если `last_withdrawal_at IS NULL`.
Единственная проверка в одном месте — нет дублирования логики.

### 🔴 SEC-02 FIXED — Повторный депозит был возможен технически
**Файл:** `api/routes/deposits.py`
Добавлена проверка: если у пользователя уже есть депозит (`deposit_amount > 0`) — запрос
отклоняется с `409 Conflict`. Один участник = один депозит = один уровень навсегда.

### 🟠 SEC-01 FIXED — Nonces хранились в памяти процесса (не работало с несколькими воркерами)
**Файл:** `security/web3_auth.py`
Nonces теперь хранятся в Redis с TTL 300 секунд.
Работает корректно при любом количестве воркеров.
Автоматический fallback на in-memory для dev-режима (одиночный воркер).

### 🟠 SEC-03 FIXED — `/api/deposits/pending` был публично доступен
**Файл:** `api/routes/deposits.py`
Добавлена проверка admin_key через query-параметр.

## Без изменений (работало корректно)
- Атомарное начисление реферальных бонусов (atomic SQL UPDATE CASE)
- Idempotency через ProcessedTransaction + IntegrityError
- Верификация USDC на блокчейне (multi-transfer attack protection)
- Ed25519 Web3-подпись при выводе
- Audit log всех финансовых операций
- Security headers, rate limiting, Argon2 хеширование
- Все 16 языков с `friends` вместо `people` в калькуляторе

## Известные задачи (требуют отдельной реализации)
- BUG-01: JWT-авторизация на всех endpoint (требует полного auth-middleware)
- SEC-04: Ограничение данных в реферальном дереве для неавторизованных
- SEC-05: Trusted proxy для X-Forwarded-For (настройка nginx)
