# 🔧 НАСТРОЙКА .env ФАЙЛА - ПОШАГОВАЯ ИНСТРУКЦИЯ

**ВАЖНО:** Все параметры ниже ОБЯЗАТЕЛЬНЫ для запуска проекта!

---

## 📋 ШАГ 1: Создайте .env файл

```bash
cp .env.example .env
nano .env  # или используйте любой редактор
```

---

## 🔑 ШАГ 2: Заполните КРИТИЧЕСКИЕ параметры

### 1. SECRET_KEY (обязательно)

**Что это:** Ключ для подписи JWT токенов

**Как сгенерировать:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Пример результата:** `xK7vQ2wR9pL3mN8tY6uE4sA1zB5cD0fH2jG9kI7lM6n`

**Куда вставить в .env:**
```bash
SECRET_KEY=xK7vQ2wR9pL3mN8tY6uE4sA1zB5cD0fH2jG9kI7lM6n
```

---

### 2. SOLANA_RPC (обязательно)

**Для тестирования (devnet):**
```bash
SOLANA_RPC=https://api.devnet.solana.com
```

**Для production (mainnet) - рекомендуется платный RPC:**

**Опция A: Alchemy** (рекомендуется)
1. Зарегистрируйтесь на https://www.alchemy.com/
2. Создайте Solana Mainnet app
3. Скопируйте HTTPS endpoint

```bash
SOLANA_RPC=https://solana-mainnet.g.alchemy.com/v2/YOUR_API_KEY
```

**Опция B: QuickNode**
1. Зарегистрируйтесь на https://www.quicknode.com/
2. Создайте Solana Mainnet endpoint
3. Скопируйте HTTP endpoint

```bash
SOLANA_RPC=https://your-endpoint.solana-mainnet.quiknode.pro/YOUR_API_KEY/
```

**Опция C: Публичный RPC (НЕ для production!):**
```bash
SOLANA_RPC=https://api.mainnet-beta.solana.com
```
⚠️ **Внимание:** Публичный RPC имеет rate limits и может быть медленным!

---

### 3. MAIN_WALLET (обязательно)

**Что это:** Адрес вашего основного кошелька для приема депозитов

**Как получить:**
1. Установите Phantom wallet: https://phantom.app/
2. Создайте кошелек
3. Скопируйте адрес (например: `7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU`)

```bash
MAIN_WALLET=7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
```

---

### 4. MAIN_WALLET_TOKEN (обязательно)

**Что это:** Адрес USDC token account вашего основного кошелька

**Как получить:**

**Способ 1: Через Solscan**
1. Откройте https://solscan.io/
2. Вставьте ваш MAIN_WALLET адрес
3. Перейдите на вкладку "Tokens"
4. Найдите USDC (EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v)
5. Скопируйте "Token Account" адрес

**Способ 2: Через код**
```python
from solana.rpc.api import Client
from solders.pubkey import Pubkey

client = Client("https://api.mainnet-beta.solana.com")
wallet = Pubkey.from_string("YOUR_MAIN_WALLET")
usdc_mint = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

response = client.get_token_accounts_by_owner(wallet, {"mint": usdc_mint})
token_account = response.value[0].pubkey
print(f"USDC Token Account: {token_account}")
```

```bash
MAIN_WALLET_TOKEN=YOUR_USDC_TOKEN_ACCOUNT_ADDRESS
```

⚠️ **Важно:** Если у вас нет USDC token account, отправьте себе минимум 0.01 USDC в Phantom, account создастся автоматически.

---

### 5. HOT_WALLET_PRIVATE_KEY (обязательно)

**Что это:** Приватный ключ hot wallet для автоматических выплат

**⚠️ КРИТИЧЕСКАЯ БЕЗОПАСНОСТЬ:**
- Создайте ОТДЕЛЬНЫЙ кошелек для hot wallet (НЕ используйте основной!)
- Храните в нем МИНИМУМ средств (например, $1000-5000)
- Регулярно выводите излишки на cold wallet
- НИКОГДА не публикуйте приватный ключ!

**Как создать hot wallet:**

**Способ 1: Solana CLI**
```bash
# Установите Solana CLI
sh -c "$(curl -sSfL https://release.solana.com/stable/install)"

# Создайте новый keypair
solana-keygen new --outfile ~/hot-wallet.json

# Получите приватный ключ в base58
solana-keygen pubkey ~/hot-wallet.json  # Это публичный адрес
# Приватный ключ в base58 находится в файле hot-wallet.json (массив чисел)
```

**Способ 2: Через Python**
```python
from solders.keypair import Keypair

# Создать новый keypair
keypair = Keypair()

print(f"Public key (wallet address): {keypair.pubkey()}")
print(f"Private key (base58): {keypair.secret().hex()}")  # Сохраните это!
```

**Куда вставить в .env:**
```bash
HOT_WALLET_PRIVATE_KEY=YOUR_BASE58_PRIVATE_KEY_HERE
```

**Пример (не используйте этот!):**
```bash
HOT_WALLET_PRIVATE_KEY=5J7WTMRo4YmVWq3H8qKjJxDyqFPhYN9K3mBL2rCvXnD8pGwE...
```

---

### 6. DATABASE_URL (обязательно)

**Формат:**
```bash
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
```

**Для локальной разработки:**
```bash
DATABASE_URL=postgresql+asyncpg://soldia_user:YOUR_STRONG_PASSWORD@localhost:5432/soldia_db
```

**Как создать БД:**
```bash
# Войдите в PostgreSQL
sudo -u postgres psql

# Создайте пользователя и БД
CREATE USER soldia_user WITH PASSWORD 'your_strong_password_123!@#';
CREATE DATABASE soldia_db OWNER soldia_user;
GRANT ALL PRIVILEGES ON DATABASE soldia_db TO soldia_user;
\q
```

**Для production (Docker):**
```bash
DATABASE_URL=postgresql+asyncpg://soldia_user:YOUR_PASSWORD@postgres:5432/soldia_db
```

**⚠️ Требования к паролю:**
- Минимум 20 символов
- Заглавные + строчные буквы
- Цифры
- Спецсимволы

---

### 7. REDIS_URL (обязательно)

**Для локальной разработки:**
```bash
REDIS_URL=redis://localhost:6379/0
```

**С паролем:**
```bash
REDIS_URL=redis://:YOUR_REDIS_PASSWORD@localhost:6379/0
```

**Для production (Docker):**
```bash
REDIS_URL=redis://:YOUR_PASSWORD@redis:6379/0
```

---

### 8. ALLOWED_ORIGINS (обязательно)

**Для development:**
```bash
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080,http://localhost:8000
```

**Для production:**
```bash
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

⚠️ **ВАЖНО:** НЕ включайте localhost в production CORS!

---

### 9. Celery (для Docker)

```bash
CELERY_BROKER_URL=redis://:YOUR_PASSWORD@redis:6379/2
CELERY_RESULT_BACKEND=redis://:YOUR_PASSWORD@redis:6379/3
```

---

### 10. Пароли для Docker services

**PostgreSQL:**
```bash
POSTGRES_USER=soldia_user
POSTGRES_PASSWORD=YOUR_STRONG_DB_PASSWORD_HERE
POSTGRES_DB=soldia_db
```

**Redis:**
```bash
REDIS_PASSWORD=YOUR_STRONG_REDIS_PASSWORD_HERE
```

---

## 📝 ШАГ 3: Опциональные параметры

### Sentry (мониторинг ошибок)
```bash
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Telegram уведомления
```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_ADMIN_CHAT_ID=123456789
```

### Email (SMTP)
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@soldia.com
```

---

## ✅ ШАГ 4: Проверка конфигурации

После заполнения .env запустите проверку:

```bash
python3 -c "from config.settings import settings, validate_configuration; validate_configuration(); print('✅ Configuration valid!')"
```

Если есть ошибки - они будут показаны с подробным описанием.

---

## 🔐 БЕЗОПАСНОСТЬ - ЧЕКЛИСТ

### Перед запуском проверьте:

- [ ] SECRET_KEY сгенерирован уникальный (НЕ дефолтный)
- [ ] HOT_WALLET_PRIVATE_KEY НЕ от основного кошелька
- [ ] Database пароль >= 20 символов
- [ ] Redis пароль >= 20 символов
- [ ] .env файл в .gitignore (НЕ коммитить!)
- [ ] ALLOWED_ORIGINS БЕЗ localhost для production
- [ ] ENVIRONMENT=production (для production)
- [ ] DEBUG=False (для production)
- [ ] В hot wallet минимум средств (например $1000-5000)
- [ ] Основной кошелек (MAIN_WALLET) в cold storage

---

## 📚 ПОЛНЫЙ ПРИМЕР .env ФАЙЛА

```bash
# ==================== ENVIRONMENT ====================
ENVIRONMENT=production
DEBUG=False

# ==================== SECRET ====================
SECRET_KEY=xK7vQ2wR9pL3mN8tY6uE4sA1zB5cD0fH2jG9kI7lM6n

# ==================== DATABASE ====================
DATABASE_URL=postgresql+asyncpg://soldia_user:MyStr0ngP@ssw0rd123!@localhost:5432/soldia_db

# ==================== REDIS ====================
REDIS_URL=redis://:MyRedisP@ss123!@localhost:6379/0

# ==================== SOLANA ====================
SOLANA_RPC=https://solana-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_API_KEY
USDC_MINT=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v

# ==================== WALLETS ====================
MAIN_WALLET=7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
MAIN_WALLET_TOKEN=4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T
HOT_WALLET_PRIVATE_KEY=5J7WTMRo4YmVWq3H8qKjJxDyqFPhYN9K3mBL2rCvXnD8pGwE...

# ==================== CORS ====================
ALLOWED_ORIGINS=https://soldia.com,https://www.soldia.com

# ==================== CELERY ====================
CELERY_BROKER_URL=redis://:MyRedisP@ss123!@localhost:6379/2
CELERY_RESULT_BACKEND=redis://:MyRedisP@ss123!@localhost:6379/3

# ==================== DOCKER ====================
POSTGRES_USER=soldia_user
POSTGRES_PASSWORD=MyStr0ngP@ssw0rd123!
POSTGRES_DB=soldia_db
REDIS_PASSWORD=MyRedisP@ss123!

# ==================== MONITORING (optional) ====================
SENTRY_DSN=https://abc123@o123.ingest.sentry.io/456
SENTRY_ENVIRONMENT=production

# ==================== NOTIFICATIONS (optional) ====================
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_ADMIN_CHAT_ID=123456789
```

---

## 🚀 СЛЕДУЮЩИЕ ШАГИ

После настройки .env:

1. **Проверьте конфигурацию:**
   ```bash
   python3 -c "from config.settings import validate_configuration; validate_configuration()"
   ```

2. **Примените миграции БД:**
   ```bash
   alembic upgrade head
   ```

3. **Запустите проект:**
   ```bash
   # Development
   uvicorn main:app --reload
   
   # Production (Docker)
   docker-compose up -d
   ```

4. **Проверьте health check:**
   ```bash
   curl http://localhost:8000/health
   ```

---

## ❓ ЧАСТЫЕ ВОПРОСЫ

### Q: Где взять Solana кошелек?
A: Установите Phantom wallet: https://phantom.app/

### Q: Как получить USDC на devnet для тестирования?
A: 
```bash
# 1. Переключитесь на devnet в Phantom
# 2. Получите devnet SOL: https://solfaucet.com/
# 3. Создайте USDC token account через SPL Token Faucet
```

### Q: Как безопасно хранить HOT_WALLET_PRIVATE_KEY?
A: Используйте AWS Secrets Manager, HashiCorp Vault или Docker Secrets. НЕ храните в .env для production!

### Q: Что делать если забыл DATABASE пароль?
A:
```bash
sudo -u postgres psql
ALTER USER soldia_user WITH PASSWORD 'new_password';
\q
```

### Q: Можно ли использовать один кошелек для MAIN_WALLET и hot wallet?
A: Технически да, но НЕ рекомендуется! Для безопасности используйте разные кошельки.

---

## 📞 ПОДДЕРЖКА

Если возникли проблемы с настройкой .env:
1. Проверьте логи: `docker-compose logs web`
2. Проверьте конфигурацию: `python -c "from config.settings import validate_configuration; validate_configuration()"`
3. Убедитесь что все параметры заполнены правильно

---

**Дата обновления:** 16 февраля 2026  
**Версия:** 2.0.0-FINAL  
**Статус:** ✅ PRODUCTION READY
