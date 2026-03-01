# SOLDIA v2.0 - Production Ready

🚀 **Реферальная платформа на блокчейне Solana с PostgreSQL, Redis и улучшенной безопасностью**

---

## 📋 Содержание

- [Основные улучшения](#основные-улучшения)
- [Технологический стек](#технологический-стек)
- [Требования](#требования)
- [Установка](#установка)
- [Конфигурация](#конфигурация)
- [Миграции БД](#миграции-бд)
- [Запуск](#запуск)
- [Безопасность](#безопасность)
- [Мониторинг](#мониторинг)
- [Production Deployment](#production-deployment)

---

## ✨ Основные улучшения

### 🗄️ База данных
- ✅ **PostgreSQL** вместо SQLite
- ✅ **SQLAlchemy 2.0** с async support
- ✅ Connection pooling (настраиваемый)
- ✅ **Alembic** для миграций
- ✅ Индексы для оптимизации запросов
- ✅ Constraints для целостности данных

### 🔴 Кэширование
- ✅ **Redis** для кэширования
- ✅ Поддержка session storage
- ✅ Rate limiting на базе Redis
- ✅ Pub/Sub для real-time updates

### 🔐 Безопасность
- ✅ **Argon2** password hashing (state-of-the-art)
- ✅ **JWT** authentication с access/refresh tokens
- ✅ Rate limiting на всех endpoint'ах
- ✅ Security headers (HSTS, CSP, XSS protection)
- ✅ Input validation и sanitization
- ✅ SQL injection protection (SQLAlchemy ORM)
- ✅ Audit logging для критичных операций
- ✅ Защита от CSRF, XSS, clickjacking

### 🏗️ Архитектура
- ✅ Модульная структура
- ✅ Async/await везде
- ✅ Dependency injection
- ✅ Централизованная конфигурация
- ✅ Proper error handling
- ✅ Structured logging

### 📊 Мониторинг
- ✅ **Sentry** интеграция для error tracking
- ✅ Health check endpoints
- ✅ Metrics и статистика
- ✅ Request/response logging

---

## 🛠 Технологический стек

### Frontend
- **HTML/CSS/JS**: Vanilla (no frameworks)
- **3D Graphics**: Three.js r128
- **Wallet Integration**: Phantom, Solflare
- **Design**: Futuristic/Cyberpunk theme
- **Responsive**: Mobile-first design

### Backend
- **Framework**: FastAPI 0.109.0
- **Database**: PostgreSQL 15+ (с asyncpg driver)
- **Cache**: Redis 7+
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Task Queue**: Celery + Redis

### Security
- **Password Hashing**: Argon2
- **JWT**: python-jose
- **Rate Limiting**: SlowAPI + Redis

### Blockchain
- **Network**: Solana Mainnet
- **Library**: solana-py 0.32.0
- **Token**: USDC (SPL Token)

### Monitoring
- **Error Tracking**: Sentry
- **Logging**: structlog

---

## 📦 Требования

### Системные требования
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- 2GB RAM минимум
- 10GB свободного места

### Для разработки
```bash
python >= 3.11
postgresql >= 15
redis >= 7
pip >= 23.0
```

---

## 🚀 Установка

### 1. Клонирование проекта

```bash
git clone <repository-url>
cd soldia_v2
```

### 2. Создание виртуального окружения

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

### 3. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Установка PostgreSQL

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### macOS
```bash
brew install postgresql@15
brew services start postgresql@15
```

#### Windows
Скачайте установщик с https://www.postgresql.org/download/windows/

### 5. Установка Redis

#### Ubuntu/Debian
```bash
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

#### macOS
```bash
brew install redis
brew services start redis
```

#### Windows
Скачайте с https://github.com/microsoftarchive/redis/releases

---

## ⚙️ Конфигурация

### 1. Создание базы данных PostgreSQL

```bash
# Подключитесь к PostgreSQL
sudo -u postgres psql

# Создайте пользователя и БД
CREATE USER soldia_user WITH PASSWORD 'your_strong_password_here';
CREATE DATABASE soldia_db OWNER soldia_user;
GRANT ALL PRIVILEGES ON DATABASE soldia_db TO soldia_user;

# Выход
\q
```

### 2. Настройка переменных окружения

```bash
# Скопируйте пример
cp .env.example .env

# Отредактируйте .env
nano .env
```

**Критически важные параметры:**

```bash
# Environment
ENVIRONMENT=production
DEBUG=False

# Secret key (генерируйте новый!)
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Database
DATABASE_URL=postgresql+asyncpg://soldia_user:your_password@localhost:5432/soldia_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Solana
SOLANA_RPC=https://api.mainnet-beta.solana.com
# Для production используйте платный RPC:
# SOLANA_RPC=https://solana-mainnet.g.alchemy.com/v2/YOUR_API_KEY

# Wallets (КРИТИЧНО!)
MAIN_WALLET=YOUR_MAIN_WALLET_ADDRESS
MAIN_WALLET_TOKEN=YOUR_USDC_TOKEN_ACCOUNT
HOT_WALLET_PRIVATE_KEY=YOUR_HOT_WALLET_PRIVATE_KEY_BASE58

# CORS
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Sentry (опционально)
SENTRY_DSN=https://your-sentry-dsn
```

**⚠️ ВАЖНО:** 
- Никогда не коммитьте `.env` в Git!
- Используйте сильные пароли
- Храните приватные ключи в secrets manager (AWS Secrets Manager, HashiCorp Vault)

---

## 🗃️ Миграции БД

### Инициализация Alembic

```bash
# Уже настроено в проекте, но если нужно заново:
alembic init alembic
```

### Создание первой миграции

```bash
# Автогенерация миграции из моделей
alembic revision --autogenerate -m "Initial migration"

# Просмотр SQL
alembic upgrade head --sql

# Применение миграции
alembic upgrade head
```

### Управление миграциями

```bash
# Создать новую миграцию
alembic revision --autogenerate -m "Add new column"

# Применить все миграции
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Показать текущую версию
alembic current

# История миграций
alembic history
```

---

## 🏃 Запуск

### Development режим

```bash
# С auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Или через Python
python main.py
```

### Production режим

```bash
# С Gunicorn (рекомендуется)
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  --log-level info

# Или напрямую с Uvicorn
uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info
```

### Проверка работоспособности

```bash
# Health check
curl http://localhost:8000/health

# Detailed health check
curl http://localhost:8000/health/detailed

# API docs (только в dev)
open http://localhost:8000/docs
```

---

## 🔒 Безопасность

### Чек-лист безопасности

- [ ] Изменен SECRET_KEY на уникальный
- [ ] Настроены ALLOWED_ORIGINS (без localhost в production)
- [ ] HOT_WALLET_PRIVATE_KEY в secrets manager
- [ ] PostgreSQL пароль >= 20 символов
- [ ] Redis защищен паролем
- [ ] HTTPS включен (SSL/TLS)
- [ ] Rate limiting активен
- [ ] Firewall настроен (только 80, 443, 22)
- [ ] Логи ротируются
- [ ] Backup настроен
- [ ] Sentry подключен

### Рекомендуемые настройки PostgreSQL

```sql
-- В postgresql.conf

max_connections = 100
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 2621kB
min_wal_size = 1GB
max_wal_size = 4GB
```

### Рекомендуемые настройки Redis

```conf
# В redis.conf

maxmemory 512mb
maxmemory-policy allkeys-lru
requirepass YOUR_STRONG_PASSWORD
bind 127.0.0.1
protected-mode yes
```

---

## 📊 Мониторинг

### Логи

```bash
# Просмотр логов приложения
tail -f logs/app.log

# Финансовые операции
tail -f financial.log

# Системные логи
journalctl -u soldia -f
```

### Метрики

Endpoint'ы для мониторинга:

```
GET /health              - Базовый health check
GET /health/detailed     - Детальный статус компонентов
```

### Sentry

Ошибки автоматически отправляются в Sentry при настройке SENTRY_DSN.

---

## 🚢 Production Deployment

### Docker (рекомендуется)

```dockerfile
# Dockerfile уже включен в проект
docker-compose up -d
```

### Systemd Service

Создайте `/etc/systemd/system/soldia.service`:

```ini
[Unit]
Description=SOLDIA API Service
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=soldia
Group=soldia
WorkingDirectory=/opt/soldia
Environment="PATH=/opt/soldia/venv/bin"
ExecStart=/opt/soldia/venv/bin/gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable soldia
sudo systemctl start soldia
sudo systemctl status soldia
```

### Nginx (reverse proxy)

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Автоматический backup

```bash
# Создайте скрипт /opt/soldia/scripts/backup.sh

#!/bin/bash
BACKUP_DIR="/backups/soldia"
DATE=$(date +%Y%m%d_%H%M%S)

# PostgreSQL backup
pg_dump -U soldia_user soldia_db | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Cleanup old backups (keep last 30 days)
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +30 -delete
```

Добавьте в crontab:

```bash
# Ежедневно в 2:00
0 2 * * * /opt/soldia/scripts/backup.sh
```

---

## 🧪 Тестирование

```bash
# Запуск тестов
pytest

# С покрытием
pytest --cov=.

# Только unit тесты
pytest tests/unit/

# Только integration тесты
pytest tests/integration/
```

---

## 📚 Дополнительные ресурсы

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Solana Documentation](https://docs.solana.com/)
- [Redis Documentation](https://redis.io/docs/)

---

## ⚠️ Важные замечания

### Юридические риски

**ВНИМАНИЕ:** Этот проект реализует MLM (Multi-Level Marketing) схему, которая:
- Может быть незаконной в вашей юрисдикции
- Требует специальных лицензий в большинстве стран
- Может быть классифицирована как финансовая пирамида

**Настоятельно рекомендуется:**
1. Проконсультироваться с юристом перед запуском
2. Получить необходимые лицензии
3. Внедрить KYC/AML процедуры
4. Рассмотреть альтернативные бизнес-модели

### Безопасность средств

- Используйте холодное хранение для основного кошелька
- Храните минимум средств в hot wallet
- Настройте multi-sig для крупных выводов
- Регулярно проводите аудит безопасности

---

## 📝 Лицензия

Proprietary - All rights reserved

---

## 👨‍💻 Автор

SOLDIA Development Team

**Версия:** 2.0.0  
**Дата:** Февраль 2025  
**Статус:** Production Ready ✅
