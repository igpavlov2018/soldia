# SOLDIA v2.3 — Bug Fix Release

## 5 критических исправлений

### CRIT-1: Race Condition → SELECT FOR UPDATE
**Файл:** `api/routes/withdrawals.py`
Два параллельных запроса проходили валидацию баланса одновременно.
Исправление: `select(User).with_for_update()` блокирует строку на время транзакции.
Второй запрос ждёт, пока первый не завершит коммит — после чего видит обновлённый баланс и отклоняется.

### CRIT-2: Rollback не восстанавливал `last_withdrawal_at`
**Файл:** `api/routes/withdrawals.py`
После `UPDATE user SET last_withdrawal_at=now` ORM-объект в памяти обновлялся.
Rollback `last_withdrawal_at=user.last_withdrawal_at` записывал то же самое новое значение, а не старое.
Исправление: `prev_last_withdrawal_at = user.last_withdrawal_at` захватывается в локальную переменную ДО любого UPDATE. Rollback использует эту переменную.

### CRIT-3: Admin-ключ в URL → в заголовке X-Admin-Key
**Файлы:** `api/routes/withdrawals.py`, `config/settings.py`
URL query-параметры логируются nginx, CloudTrail, Sentry, браузером.
Исправление: ключ передаётся только в заголовке `X-Admin-Key`, никогда в URL.
Сравнение через `hmac.compare_digest` — защита от timing-атак.
Добавлена отдельная переменная `ADMIN_API_KEY` (не производная от `SECRET_KEY`).

### CRIT-4: IP-spoofing в rate limiting
**Файлы:** `security/auth.py`, `api/routes/withdrawals.py`, `api/routes/referrals.py`
`X-Forwarded-For` — это список IP, первый из которых задаётся клиентом.
Исправление: используется `X-Real-IP`, устанавливаемый nginx из `$remote_addr`.
nginx конфиг должен содержать: `proxy_set_header X-Real-IP $remote_addr;`

### CRIT-5: Redis GETDEL → GET+DEL pipeline (Redis 4.0+ совместимость)
**Файл:** `security/web3_auth.py`
`GETDEL` появился в Redis 6.2. На Redis 5.x / 6.0 / 6.1 команда падает.
Ошибка молча уходила в in-memory fallback — открывая DoS-вектор.
Исправление: `pipeline(transaction=False)` с `GET` + `DELETE` — эффективно атомарно
(Redis однопоточный, команды пайплайна выполняются последовательно).
Совместимо с Redis 4.0+. При недоступности Redis — `RuntimeError`, не silent fallback.

## 8 серьёзных исправлений

### SER-1: Idempotency для выводов
Добавлено поле `idempotency_key` в модель `Withdrawal` (уникальный индекс).
Клиент передаёт уникальный ключ в каждой попытке вывода.
Повторный запрос с тем же ключом возвращает результат первого — без повторной обработки.

### SER-2: float() в финансовых расчётах → Decimal и str
Все суммы вычисляются через `Decimal`. В JSON возвращаются как строки (`str(amount)`) — не теряется точность при сериализации.

### SER-3: N+1 запросы в referrals → батчевые IN-запросы
Старый `build_referral_tree`: для каждого узла дерева отдельный SELECT.
100 L1 × 10 L2 = 1100+ запросов.
Новый `build_referral_tree_flat`: ровно 3 запроса независимо от размера дерева.
L1: WHERE referrer_id = root | L2: WHERE referrer_id IN (l1_ids) | L3: аналогично.

### SER-4: float() в referrals → str
Все `float(user.earned_l1)` заменены на `str(user.earned_l1)`.

### SER-5: Redis KEYS() → SCAN
`KEYS(pattern)` блокирует весь Redis event loop (O(N) по всем ключам).
Заменено на cursor-based `SCAN` с батчами по 100 ключей.
Добавлен async-генератор `scan_keys()` для итерации без блокировки.
