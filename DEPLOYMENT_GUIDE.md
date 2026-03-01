# 🚀 DEPLOYMENT GUIDE - SOLDIA v2.0 COMPLETE

## ✅ What's Included (100% Ready!)

This package now includes **EVERYTHING** needed for production:

- ✅ API Routes (users, deposits, withdrawals, referrals)
- ✅ Celery Tasks (background processing)
- ✅ Solana Integration (blockchain client)
- ✅ Nginx Configuration (production proxy)
- ✅ Database Migrations (Alembic)
- ✅ Tests (pytest suite)
- ✅ All 10 Solana Wallets in frontend
- ✅ Complete documentation

---

## 📋 Quick Start (3 Commands)

```bash
# 1. Extract
tar -xzf soldia_v2_complete.tar.gz
cd soldia_v2_complete

# 2. Configure
cp .env.example .env
nano .env  # Edit your settings

# 3. Deploy
./deploy.sh
```

**That's it!** 🎉

Access at: http://localhost:8000

---

## 🔧 Configuration (.env)

**REQUIRED Settings:**

```bash
# Database
POSTGRES_PASSWORD=your_secure_password_here
DATABASE_URL=postgresql+asyncpg://soldia_user:your_secure_password_here@postgres:5432/soldia_db

# Redis
REDIS_PASSWORD=your_redis_password_here
REDIS_URL=redis://:your_redis_password_here@redis:6379/0

# Security
SECRET_KEY=your_256_bit_secret_key_here

# Solana
MAIN_WALLET=your_main_wallet_address
MAIN_WALLET_TOKEN=your_main_wallet_usdc_token_account
HOT_WALLET_PRIVATE_KEY=your_hot_wallet_private_key  # For withdrawals
```

**Optional Settings:**

```bash
# Environment
ENVIRONMENT=production
DEBUG=False

# Monitoring
SENTRY_DSN=your_sentry_dsn

# Notifications
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
SMTP_HOST=smtp.gmail.com
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

---

## 🗄️ Database Setup

### Option 1: Automatic (via deploy.sh)

```bash
./deploy.sh
```

Migrations run automatically!

### Option 2: Manual

```bash
# Start database
docker-compose up -d postgres redis

# Run migrations
docker-compose exec api alembic upgrade head

# Or use migration script
./migrate.sh
```

---

## 🔐 SSL Certificates (Production)

### Let's Encrypt (Recommended)

```bash
# Install certbot
sudo apt-get install certbot

# Get certificate
sudo certbot certonly --standalone -d your-domain.com

# Copy to project
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./nginx/ssl/cert.pem
cp /etc/letsencrypt/live/your-domain.com/privkey.pem ./nginx/ssl/key.pem

# Enable HTTPS in nginx.conf
nano nginx/nginx.conf  # Uncomment HTTPS server block

# Restart
docker-compose restart nginx
```

---

## 🧪 Testing

```bash
# Run all tests
docker-compose exec api pytest

# Run with coverage
docker-compose exec api pytest --cov=. --cov-report=html

# View coverage report
open htmlcov/index.html
```

---

## 📊 Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Detailed health
curl http://localhost:8000/health/detailed

# Database stats
curl http://localhost:8000/health/detailed | jq .components.database
```

### Celery Flower (Task Monitoring)

Access at: http://localhost:5555

Default credentials: None (add auth in production!)

### Logs

```bash
# View all logs
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f celery_worker
docker-compose logs -f nginx
```

---

## 🔄 Celery Tasks

### Check Status

```bash
# List active tasks
docker-compose exec celery_worker celery -A tasks.worker inspect active

# List scheduled tasks
docker-compose exec celery_beat celery -A tasks.worker inspect scheduled
```

### Manual Task Execution

```python
from tasks.deposits import check_pending_deposits
from tasks.withdrawals import process_pending_withdrawals

# Trigger manually
check_pending_deposits.delay()
process_pending_withdrawals.delay()
```

---

## 🌐 API Endpoints

### Users
- `POST /api/users/register` - Register new user
- `GET /api/users/stats/{wallet}` - Get user stats
- `GET /api/users/history/{wallet}` - Get transaction history

### Deposits
- `POST /api/deposits/verify` - Verify and process deposit
- `GET /api/deposits/pending` - List pending deposits

### Withdrawals
- `POST /api/withdrawals/request` - Request withdrawal
- `GET /api/withdrawals/status/{id}` - Check withdrawal status
- `GET /api/withdrawals/list/{wallet}` - List user withdrawals

### Referrals
- `GET /api/referrals/tree/{wallet}` - Get referral tree
- `GET /api/referrals/stats/{wallet}` - Get referral statistics

### Documentation
- `GET /docs` - Swagger UI (only in DEBUG mode)
- `GET /redoc` - ReDoc (only in DEBUG mode)

---

## 🚨 Troubleshooting

### Database Connection Error

```bash
# Check if database is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Restart database
docker-compose restart postgres
```

### Celery Won't Start

```bash
# Check configuration
docker-compose exec api python -c "from tasks.worker import celery; print(celery.conf)"

# Check broker connection
docker-compose exec celery_worker celery -A tasks.worker inspect ping
```

### Nginx 502 Error

```bash
# Check if API is running
docker-compose ps api

# Check API logs
docker-compose logs api

# Test API directly
curl http://localhost:8000/health
```

---

## 🔧 Maintenance

### Backup Database

```bash
# Create backup
docker-compose exec postgres pg_dump -U soldia_user soldia_db > backup.sql

# Restore backup
docker-compose exec -T postgres psql -U soldia_user soldia_db < backup.sql
```

### Update Code

```bash
# Pull changes
git pull

# Rebuild
docker-compose build

# Restart
docker-compose up -d

# Run new migrations
docker-compose exec api alembic upgrade head
```

### Scale Workers

```bash
# Scale celery workers
docker-compose up -d --scale celery_worker=3
```

---

## 📈 Production Checklist

Before going live:

- [ ] Change all default passwords in .env
- [ ] Set ENVIRONMENT=production
- [ ] Set DEBUG=False
- [ ] Configure SSL certificates
- [ ] Set up Sentry for error tracking
- [ ] Configure SMTP for email notifications
- [ ] Set up automated backups
- [ ] Configure firewall rules
- [ ] Set up monitoring (Grafana/Prometheus)
- [ ] Test all API endpoints
- [ ] Run security audit
- [ ] Load test the application

---

## 🎯 Next Steps

1. **Configure Solana Integration**
   - Add your main wallet address
   - Add hot wallet private key for withdrawals
   - Test on devnet first!

2. **Set Up Monitoring**
   - Configure Sentry
   - Set up Prometheus + Grafana
   - Configure alerts

3. **Security Audit**
   - Run penetration tests
   - Review access logs
   - Test rate limiting

4. **Performance Testing**
   - Load testing with 1000+ concurrent users
   - Database query optimization
   - Cache effectiveness

---

## 📞 Support

Need help? Check:

- README.md - Detailed documentation
- QUICKSTART.md - Quick start guide
- IMPROVEMENTS.md - List of changes
- API docs - http://localhost:8000/docs

---

**Last Updated:** February 12, 2026
**Version:** 2.0.0 Complete
**Status:** ✅ PRODUCTION READY
