# 🚀 SOLDIA v2.0 - Quick Start Guide

Быстрый старт за 5 минут!

---

## 📦 Что в архиве?

```
soldia_v2/
├── 📱 main.py              - Главное приложение FastAPI
├── ⚙️  config/             - Конфигурация
├── 🗄️  models/             - Модели базы данных
├── 💾 database/           - Database manager (PostgreSQL)
├── 🔴 cache/              - Cache manager (Redis)
├── 🔐 security/           - Безопасность и аутентификация
├── 🐳 Dockerfile          - Docker образ
├── 🎼 docker-compose.yml  - Оркестрация сервисов
├── 🚀 deploy.sh           - Автоматический деплой
├── 📚 README.md           - Полная документация
└── 📊 IMPROVEMENTS.md     - Список улучшений
```

---

## ⚡ Быстрый старт (Docker)

### Вариант 1: С Docker (рекомендуется)

```bash
# 1. Распакуйте архив
tar -xzf soldia_v2_production.tar.gz
cd soldia_v2

# 2. Настройте переменные окружения
cp .env.example .env
nano .env  # Отредактируйте критичные параметры

# 3. Запустите
./deploy.sh
```

**Вот и всё!** 🎉

Сервисы доступны на:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

---

## 🛠️ Быстрый старт (без Docker)

### Требования
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Шаги

```bash
# 1. Распакуйте и перейдите в папку
tar -xzf soldia_v2_production.tar.gz
cd soldia_v2

# 2. Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Настройте БД PostgreSQL
sudo -u postgres psql
CREATE USER soldia_user WITH PASSWORD 'your_password';
CREATE DATABASE soldia_db OWNER soldia_user;
GRANT ALL PRIVILEGES ON DATABASE soldia_db TO soldia_user;
\q

# 5. Настройте .env
cp .env.example .env
nano .env

# 6. Запустите миграции
alembic upgrade head

# 7. Запустите приложение
python main.py
```

---

## ⚙️ Минимальная конфигурация .env

Обязательно измените эти параметры:

```bash
# Секретный ключ (сгенерируйте новый!)
SECRET_KEY=your-secret-key-here

# База данных
DATABASE_URL=postgresql+asyncpg://soldia_user:password@localhost:5432/soldia_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Solana кошельки
MAIN_WALLET=YOUR_MAIN_WALLET_ADDRESS
MAIN_WALLET_TOKEN=YOUR_USDC_TOKEN_ACCOUNT
HOT_WALLET_PRIVATE_KEY=YOUR_HOT_WALLET_KEY

# CORS (ваш домен)
ALLOWED_ORIGINS=https://yourdomain.com
```

**Генерация SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 🧪 Проверка установки

### 1. Health Check
```bash
curl http://localhost:8000/health
```

Ожидаемый ответ:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "environment": "development"
}
```

### 2. Detailed Health
```bash
curl http://localhost:8000/health/detailed
```

### 3. API Documentation
Откройте в браузере:
```
http://localhost:8000/docs
```

---

## 🎯 Что дальше?

### 1. Изучите документацию
```bash
less README.md
less IMPROVEMENTS.md
```

### 2. Просмотрите логи
```bash
# Docker
docker-compose logs -f

# Без Docker
tail -f logs/app.log
tail -f financial.log
```

### 3. Проверьте безопасность

Обязательные проверки:
- [ ] Изменен SECRET_KEY
- [ ] Настроены wallet addresses
- [ ] Настроен CORS (без localhost)
- [ ] Установлены сильные пароли
- [ ] Включен HTTPS (для production)

---

## 📊 Основные endpoint'ы

```
GET  /health              - Health check
GET  /health/detailed     - Detailed status
GET  /docs                - API documentation (dev only)

# Пользователи
POST /api/users/register  - Регистрация
GET  /api/users/{wallet}  - Информация о пользователе

# Депозиты
POST /api/deposits/verify - Верификация депозита

# Выводы
POST /api/withdrawals     - Запрос на вывод
GET  /api/withdrawals     - История выводов

# Статистика
GET  /api/stats/{wallet}  - Статистика пользователя
```

---

## 🐛 Troubleshooting

### Проблема: База данных не подключается

**Решение:**
```bash
# Проверьте статус PostgreSQL
sudo systemctl status postgresql

# Проверьте что БД создана
sudo -u postgres psql -l
```

### Проблема: Redis не работает

**Решение:**
```bash
# Проверьте статус Redis
sudo systemctl status redis

# Проверьте подключение
redis-cli ping
```

### Проблема: Docker containers не стартуют

**Решение:**
```bash
# Проверьте логи
docker-compose logs

# Пересоздайте контейнеры
docker-compose down
docker-compose up -d --force-recreate
```

---

## 📞 Полезные команды

### Docker
```bash
# Просмотр статуса
docker-compose ps

# Логи всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f api

# Остановка
docker-compose down

# Полная очистка
docker-compose down -v
```

### База данных
```bash
# Подключение к PostgreSQL в Docker
docker-compose exec postgres psql -U soldia_user -d soldia_db

# Backup
docker-compose exec postgres pg_dump -U soldia_user soldia_db > backup.sql

# Restore
docker-compose exec -T postgres psql -U soldia_user soldia_db < backup.sql
```

### Alembic
```bash
# Создать миграцию
alembic revision --autogenerate -m "Description"

# Применить миграции
alembic upgrade head

# Откатить последнюю
alembic downgrade -1

# История
alembic history
```

---

## 🔐 Security Checklist

Перед production запуском:

- [ ] ✅ Изменить все дефолтные пароли
- [ ] ✅ Сгенерировать новый SECRET_KEY
- [ ] ✅ Настроить HTTPS (SSL/TLS)
- [ ] ✅ Настроить firewall
- [ ] ✅ Включить rate limiting
- [ ] ✅ Настроить backup
- [ ] ✅ Подключить Sentry
- [ ] ✅ Убрать localhost из ALLOWED_ORIGINS
- [ ] ✅ Перевести DEBUG=False
- [ ] ✅ Проверить логирование

---

## 📚 Дополнительные ресурсы

- **Полная документация:** README.md
- **Список улучшений:** IMPROVEMENTS.md
- **Конфигурация:** .env.example
- **API документация:** http://localhost:8000/docs

---

## 💡 Tips & Tricks

### 1. Быстрый restart
```bash
docker-compose restart api
```

### 2. Очистка логов
```bash
truncate -s 0 logs/app.log
truncate -s 0 financial.log
```

### 3. Мониторинг ресурсов
```bash
docker stats
```

### 4. Проверка портов
```bash
netstat -tulpn | grep -E '8000|5432|6379'
```

---

## ✅ Checklist для Production

### Before Deploy
- [ ] .env файл настроен
- [ ] Пароли изменены
- [ ] SSL сертификаты установлены
- [ ] Firewall настроен
- [ ] Backup настроен

### After Deploy
- [ ] Health check проходит
- [ ] Логи чистые (без ошибок)
- [ ] Sentry получает события
- [ ] Все сервисы запущены
- [ ] Тесты проходят

---

## 🎉 Готово!

Теперь у вас есть:
- ✅ Production-ready API
- ✅ PostgreSQL database
- ✅ Redis cache
- ✅ Enhanced security
- ✅ Docker deployment
- ✅ Monitoring & logging

**Удачи с запуском!** 🚀

---

**Quick Links:**
- GitHub Issues: (укажите ссылку)
- Documentation: README.md
- Support: (укажите контакт)
