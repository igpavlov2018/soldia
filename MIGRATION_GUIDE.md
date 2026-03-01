# 🚀 SOLDIA v2.1 MODERNIZATION GUIDE

## Overview

Это руководство описывает все изменения, сделанные для модернизации SOLDIA v2.0. Изменения включают:

✅ **Атомарное обновление referral earnings** (fix race condition)  
✅ **AWS KMS интеграция** для управления приватными ключами  
✅ **Защита от multi-transfer атак** в blockchain верификации  
✅ **Многоуровневая валидация withdrawals** (threshold, limits, frequency)  
✅ **Улучшенная Web3 аутентификация** с signature verification  
✅ **Обновленная конфигурация** с AWS поддержкой  

---

## 📋 ФАЙЛЫ, КОТОРЫЕ НУЖНО ОБНОВИТЬ

### 1. **deposits.py** → **deposits_FIXED.py**

**Изменения:**
- ✅ Атомарные UPDATE операции с `CASE` логикой
- ✅ Однопроходная обработка всех уровней referral
- ✅ Нет race condition при конкурентных депозитах

**Как внедрить:**
```bash
# Backup старого файла
cp api/routes/deposits.py api/routes/deposits.py.backup

# Скопировать исправленную версию
cp deposits_FIXED.py api/routes/deposits.py

# Обновить импорты (если нужно)
# - Все остальное остается прежним
```

**Проверка:**
```python
# В тестах убедитесь, что:
# 1. Concurrent deposits не вызывают ошибок
# 2. Referral earnings правильно начисляются
# 3. Threshold флаг устанавливается атомарно
pytest tests/test_deposits.py -v
```

---

### 2. **security/key_management.py** (NEW FILE)

**Что это:**
Новая система управления приватными ключами через AWS KMS

**Как внедрить:**
```bash
# Создать новый файл
cp key_management.py security/key_management.py

# Добавить в security/__init__.py:
# from security.key_management import get_key_manager, KeyManagementSystem

# Обновить blockchain/solana_client.py для использования KMS
```

**Конфигурация в .env:**
```env
# AWS KMS Configuration
USE_AWS_KMS=true
AWS_REGION=us-east-1
KMS_KEY_ID=arn:aws:kms:us-east-1:ACCOUNT_ID:key/12345678-1234-1234-1234-123456789012
HOT_WALLET_PRIVATE_KEY=  # Leave empty when using KMS
```

**Первоначальная настройка:**
```bash
# 1. Создать AWS KMS key (если не существует)
aws kms create-key --region us-east-1 --description "SOLDIA Hot Wallet Key"

# 2. Сохранить приватный ключ в Parameter Store
aws ssm put-parameter \
  --name "/soldia/hot-wallet-private-key" \
  --value "YOUR_BASE58_PRIVATE_KEY" \
  --type "SecureString" \
  --key-id "arn:aws:kms:..." \
  --region us-east-1

# 3. Проверить доступ
aws ssm get-parameter \
  --name "/soldia/hot-wallet-private-key" \
  --with-decryption \
  --region us-east-1
```

**IAM Policy (для приложения):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KMSKeyUsage",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT_ID:key/KEY_ID"
    },
    {
      "Sid": "ParameterStoreAccess",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:PutParameter"
      ],
      "Resource": "arn:aws:ssm:us-east-1:ACCOUNT_ID:parameter/soldia/*"
    }
  ]
}
```

---

### 3. **blockchain/solana_client.py** → **solana_client_FIXED.py**

**Изменения:**
- ✅ Защита от multi-transfer атак
- ✅ Проверка количества USDC transfers (должно быть ровно 1)
- ✅ Поддержка AWS KMS для приватных ключей
- ✅ Лучший обработка ошибок

**Как внедрить:**
```bash
# Backup старого файла
cp blockchain/solana_client.py blockchain/solana_client.py.backup

# Скопировать исправленную версию
cp solana_client_FIXED.py blockchain/solana_client.py

# Установить зависимости
pip install -r requirements_UPDATED.txt
```

**Ключевые изменения в коде:**
```python
# Старое (уязвимо для multi-transfer атак):
for instruction in instructions:
    if parsed.get('type') in ['transfer', 'transferChecked']:
        # Берет ПЕРВЫЙ transfer и break
        actual_recipient = destination
        break

# Новое (защищено):
usdc_transfers = []  # Track ALL transfers
for instruction in instructions:
    if parsed.get('type') in ['transfer', 'transferChecked']:
        # Recordает ВСЕ transfers
        usdc_transfers.append({...})

# Validate exactly ONE transfer
if len(usdc_transfers) != 1:
    return {"valid": False, "error": "Multiple transfers detected"}
```

**Проверка:**
```bash
# Тестировать на testnet
SOLANA_RPC="https://api.devnet.solana.com" python -m pytest tests/test_blockchain.py
```

---

### 4. **api/routes/withdrawals.py** → **withdrawals_FIXED.py**

**Изменения:**
- ✅ Многоуровневая валидация (threshold, limits, frequency, balance)
- ✅ Проверка платформы balance
- ✅ Web3 signature verification
- ✅ Статистика withdrawals endpoint

**Как внедрить:**
```bash
# Создать новый файл withdrawals
cp withdrawals_FIXED.py api/routes/withdrawals.py

# Обновить api/routes/__init__.py:
# from api.routes.withdrawals import router as withdrawals_router

# Обновить main.py:
# from api.routes import withdrawals_router
# app.include_router(
#     withdrawals_router,
#     prefix=f"{settings.API_PREFIX}/withdrawals",
#     tags=["Withdrawals"]
# )
```

**Новые rate limits:**
```python
@limiter.limit("5/day")  # Max 5 withdrawals per day
async def withdraw_funds(...):
```

**Новые эндпоинты:**
```bash
# Получить статистику withdrawals
GET /api/withdrawals/stats?wallet_address=...

# Ответ:
{
  "wallet": "...",
  "deposit_amount": 49.00,
  "total_earned": 120.50,
  "total_withdrawn": 50.00,
  "available": 70.50,
  "withdrawal_threshold": 98.00,  # 2x deposit
  "threshold_met": true,
  "daily_limit": 10000.00,
  "daily_withdrawn": 500.00,
  "daily_remaining": 9500.00,
  "monthly_limit": 100000.00,
  "monthly_withdrawn": 2000.00,
  "monthly_remaining": 98000.00,
  "last_withdrawal": "2026-02-17T10:30:00"
}
```

---

### 5. **config/settings.py** → **settings_UPDATED.py**

**Изменения:**
- ✅ AWS KMS поддержка (USE_AWS_KMS, AWS_REGION, KMS_KEY_ID)
- ✅ Withdrawal limits (DAILY_WITHDRAWAL_LIMIT, MONTHLY_WITHDRAWAL_LIMIT, WITHDRAWAL_FREQUENCY_HOURS)
- ✅ Полная валидация конфигурации
- ✅ Версия обновлена до 2.1.0

**Как внедрить:**
```bash
# Backup старого файла
cp config/settings.py config/settings.py.backup

# Скопировать обновленную версию
cp settings_UPDATED.py config/settings.py
```

**Новые переменные окружения:**
```env
# AWS KMS (для production)
USE_AWS_KMS=true
AWS_REGION=us-east-1
KMS_KEY_ID=arn:aws:kms:us-east-1:ACCOUNT_ID:key/...

# Withdrawal Limits
DAILY_WITHDRAWAL_LIMIT=10000
MONTHLY_WITHDRAWAL_LIMIT=100000
WITHDRAWAL_FREQUENCY_HOURS=24
```

---

### 6. **security/web3_auth.py** → **web3_auth_IMPROVED.py**

**Изменения:**
- ✅ Улучшенная проверка Ed25519 подписей
- ✅ Валидация формата сообщения
- ✅ Проверка timestamp
- ✅ Nonce обработка с TTL
- ✅ Лучший обработка ошибок

**Как внедрить:**
```bash
# Backup старого файла
cp security/web3_auth.py security/web3_auth.py.backup

# Скопировать улучшенную версию
cp web3_auth_IMPROVED.py security/web3_auth.py

# Обновить импорты в других файлах:
# from security.web3_auth import verify_solana_signature, create_auth_message
```

**Использование:**
```python
from security.web3_auth import Web3Auth, verify_solana_signature

# Получить Web3Auth instance
web3_auth = Web3Auth()

# Сгенерировать nonce
nonce = web3_auth.generate_nonce()

# Создать сообщение для подписи
message = create_auth_message(wallet_address, nonce)

# Клиент подписывает сообщение своим приватным ключом

# Сервер проверяет подпись
is_valid = await verify_solana_signature(
    message=message,
    signature=signature,  # Base58-encoded
    wallet=wallet_address
)
```

---

### 7. **requirements.txt** → **requirements_UPDATED.txt**

**Изменения:**
- ✅ Добавлены boto3 и botocore для AWS
- ✅ Добавлены json-logger для структурированного логирования
- ✅ Удалены deprecated пакеты
- ✅ Обновлены версии

**Как внедрить:**
```bash
# Обновить dependencies
pip install -r requirements_UPDATED.txt

# Или для development
pip install -r requirements_UPDATED.txt
pip install black flake8 mypy bandit pylint
```

---

## 🔄 ПОШАГОВАЯ МИГРАЦИЯ

### День 1: Подготовка

```bash
# 1. Создать backup текущей версии
git tag -a v2.0.0-backup -m "Backup before modernization"

# 2. Создать branch для изменений
git checkout -b modernize/v2.1.0

# 3. Обновить requirements
pip install -r requirements_UPDATED.txt
```

### День 2: Критические исправления

```bash
# 1. Обновить deposits.py (fix race condition)
cp deposits_FIXED.py api/routes/deposits.py

# 2. Обновить solana_client.py (prevent multi-transfer)
cp solana_client_FIXED.py blockchain/solana_client.py

# 3. Обновить settings.py
cp settings_UPDATED.py config/settings.py

# 4. Запустить тесты
pytest tests/ -v
```

### День 3: Новые функции

```bash
# 1. Добавить key management system
cp key_management.py security/key_management.py

# 2. Обновить Web3 auth
cp web3_auth_IMPROVED.py security/web3_auth.py

# 3. Переписать withdrawals
cp withdrawals_FIXED.py api/routes/withdrawals.py

# 4. Протестировать все
pytest tests/ -v --cov
```

### День 4: AWS KMS Настройка

```bash
# 1. Создать KMS key (если используется AWS)
aws kms create-key --region us-east-1

# 2. Сохранить приватный ключ
aws ssm put-parameter \
  --name "/soldia/hot-wallet-private-key" \
  --value "YOUR_KEY" \
  --type "SecureString"

# 3. Проверить доступ
python -c "
from security.key_management import get_key_manager
import asyncio

async def test():
    km = get_key_manager()
    key = await km.get_private_key()
    print('✅ KMS working')

asyncio.run(test())
"
```

### День 5: Полное тестирование

```bash
# 1. Запустить все тесты
pytest tests/ -v --cov=100

# 2. Запустить security checks
bandit -r api/ blockchain/ security/

# 3. Type checking
mypy api/ blockchain/ security/ --strict

# 4. Load testing
# python load_test.py
```

### День 6: Deployment

```bash
# 1. Merge в main
git merge modernize/v2.1.0

# 2. Tag new version
git tag -a v2.1.0 -m "Modernized security and performance"

# 3. Deploy на staging
docker build -t soldia:v2.1.0 .
docker push registry/soldia:v2.1.0

# 4. Run migrations
alembic upgrade head

# 5. Deploy на production
# (follow your deployment process)
```

---

## ✅ VERIFICATION CHECKLIST

```
[ ] Все тесты проходят
[ ] Code coverage ≥ 90%
[ ] Нет security warnings (bandit)
[ ] Type hints OK (mypy)
[ ] Формат кода OK (black)
[ ] Линтер OK (flake8, pylint)
[ ] Load test successful (1000+ concurrent users)
[ ] Database migrations OK
[ ] AWS KMS configured (if using)
[ ] Monitoring/alerting configured
[ ] Documentation updated
[ ] Release notes prepared
[ ] Backup created
```

---

## 🐛 TROUBLESHOOTING

### Issue: Race condition still happening

**Solution:**
```python
# Check that you're using RETURNING clause
stmt = (
    update(User)
    .where(...)
    .values(...)
    .returning(User)  # THIS IS CRITICAL
)
```

### Issue: AWS KMS key not found

**Solution:**
```bash
# List available keys
aws kms list-keys --region us-east-1

# Verify key has correct policy
aws kms get-key-policy \
  --key-id arn:aws:kms:... \
  --policy-name default
```

### Issue: Multi-transfer not detected

**Solution:**
```python
# Ensure you're collecting ALL transfers
usdc_transfers = []  # NOT a single variable

for instruction in instructions:
    if is_usdc_transfer:
        usdc_transfers.append(...)  # Append, don't break

# Then validate length
if len(usdc_transfers) != 1:
    return error
```

### Issue: Signature verification failing

**Solution:**
```python
# Check signature is properly base58 decoded
signature_bytes = base58.b58decode(signature)
assert len(signature_bytes) == 64  # Ed25519 must be 64 bytes

# Check public key is properly decoded
public_key_bytes = base58.b58decode(wallet_address)
assert len(public_key_bytes) == 32  # Ed25519 must be 32 bytes
```

---

## 📚 DOCUMENTATION

All new functions have docstrings. Generate documentation:

```bash
# Install sphinx
pip install sphinx

# Generate HTML docs
sphinx-build -b html docs/ docs/_build/

# View in browser
open docs/_build/index.html
```

---

## 🎯 POST-DEPLOYMENT

1. **Monitor logs** for any errors
2. **Check metrics** - latency, error rate, DB performance
3. **Verify withdrawals** are working correctly
4. **Test referral earnings** with test transactions
5. **Confirm rate limiting** is functioning
6. **Review audit logs** for any suspicious activity

---

## 📞 SUPPORT

If you encounter issues during migration:

1. Check this guide for troubleshooting
2. Review detailed comments in each file
3. Run tests with verbose logging
4. Check AWS CloudTrail for KMS errors
5. Review Sentry for application errors

---

**Version:** 2.1.0  
**Last Updated:** February 17, 2026  
**Status:** READY FOR PRODUCTION
