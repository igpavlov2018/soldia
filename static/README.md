# SOLDIA v2.0 - Frontend

## 📁 Static Files Structure

```
static/
├── index.html          # Main frontend page (4236 lines)
├── api-config.js       # API configuration and helper functions
└── README.md          # This file
```

## 🔗 Integration with Backend

### API Endpoints используемые фронтендом:

#### Health & Config
- `GET /health` - Basic health check
- `GET /api/config` - Get public configuration

#### Users
- `POST /api/users/register` - Register new user
- `GET /api/stats/{wallet}` - Get user statistics
- `GET /api/stats/detailed/{wallet}` - Get detailed stats

#### Deposits
- `POST /api/deposits/verify` - Verify deposit transaction

#### Withdrawals
- `POST /api/withdrawals` - Request withdrawal
- `GET /api/withdrawals/{wallet}` - Get withdrawal history

#### Demo Mode
- `GET /api/demo/stats` - Demo statistics
- `GET /api/demo/stats/detailed` - Demo detailed stats

## 🎨 Features

### Оригинальный HTML включает:

1. **3D Wave Background** (Three.js)
   - Динамический 3D фон с волнами
   - Particle effects
   - Futuristic design

2. **Wallet Integration**
   - Phantom wallet
   - Solflare wallet
   - Solana blockchain interaction

3. **Dashboard**
   - User tier display (Topaz/Opal/Sapphire/Diamond)
   - Referral link with copy function
   - Earnings statistics
   - Withdrawal interface

4. **Multi-language Support**
   - English
   - Russian (Русский)

5. **Demo Mode**
   - Try dashboard without wallet connection
   - Sample data visualization

## 🔧 Configuration

### API Base URL

По умолчанию фронтенд использует текущий домен:
```javascript
baseUrl: window.location.origin
```

Для разработки вы можете изменить в `api-config.js`:
```javascript
baseUrl: 'http://localhost:8000'
```

### CORS

Убедитесь что ваш домен добавлен в `ALLOWED_ORIGINS` в `.env`:
```bash
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

## 🚀 How to Use

### Development (с auto-reload)

```bash
# Запустите backend
python main.py

# Откройте в браузере
http://localhost:8000
```

Frontend автоматически обслуживается FastAPI.

### Production (with Nginx)

Nginx конфигурация уже включена в `docker-compose.yml`:

```nginx
location / {
    root /usr/share/nginx/html;
    try_files $uri $uri/ /index.html;
}

location /api {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

## 📝 Customization

### Изменить API endpoints

Отредактируйте `api-config.js`:
```javascript
const API_CONFIG = {
    baseUrl: 'https://api.yourdomain.com',
    endpoints: {
        // ... ваши endpoints
    }
};
```

### Изменить цвета/стили

В `index.html` найдите CSS переменные:
```css
:root {
    --neon-cyan: #00F0FF;
    --neon-pink: #FF10F0;
    --neon-purple: #B026FF;
    /* ... */
}
```

### Изменить уровни

В `index.html` найдите секцию с ценами:
```html
<!-- Tier cards with prices -->
```

Или получите цены из API:
```javascript
const config = await API.getConfig();
const levels = config.config.levels;
```

## 🐛 Debugging

### Включить debug режим

В браузере откройте Console (F12) и выполните:
```javascript
localStorage.setItem('debug', 'true');
```

### Проверить API соединение

```javascript
// Test health check
API.healthCheck().then(console.log);

// Test config
API.getConfig().then(console.log);

// Test demo mode
API.getDemoStats().then(console.log);
```

## 🔒 Security Notes

### CSP (Content Security Policy)

Backend настроен с CSP headers. Если добавляете внешние скрипты, обновите CSP в `main.py`:

```python
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    # Add your CDN here
)
```

### HTTPS

В production ВСЕГДА используйте HTTPS:
- Wallet connections требуют HTTPS
- JWT tokens требуют secure connection
- Blockchain interactions требуют HTTPS

## 📱 Mobile Support

HTML полностью адаптивен и работает на:
- Desktop (1920px+)
- Tablet (768px - 1920px)
- Mobile (320px - 768px)

## 🎯 Next Steps

1. **Customization**
   - Измените логотип
   - Обновите цветовую схему
   - Добавьте ваш контент

2. **Testing**
   - Протестируйте все функции
   - Проверьте на разных устройствах
   - Проверьте wallet connections

3. **Deployment**
   - Настройте домен
   - Настройте SSL/TLS
   - Настройте CDN (опционально)

## 📚 Dependencies

### Внешние библиотеки (загружаются с CDN):

- **Three.js** (r128) - 3D graphics
  ```html
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  ```

- **Google Fonts**
  - Orbitron
  - Rajdhani
  - Exo 2

### Wallet SDKs

Подключаются через браузерные расширения:
- Phantom Wallet
- Solflare Wallet

## 💡 Tips

### Performance

1. **Включите Gzip** - уже настроено в main.py
2. **Используйте CDN** для статики (опционально)
3. **Кэшируйте static assets** в Nginx

### SEO

Добавьте в `<head>` секцию:
```html
<meta name="description" content="Your description">
<meta property="og:title" content="SOLDIA">
<meta property="og:description" content="...">
<meta property="og:image" content="/static/og-image.png">
```

## 🆘 Troubleshooting

### Problem: API calls failing

**Solution:**
1. Проверьте CORS settings в `.env`
2. Проверьте `api-config.js` baseUrl
3. Откройте Browser Console для деталей

### Problem: Wallet not connecting

**Solution:**
1. Убедитесь что используете HTTPS (не localhost)
2. Проверьте что расширение wallet установлено
3. Проверьте Browser Console

### Problem: Styles not loading

**Solution:**
1. Проверьте что static directory смонтирован
2. Hard refresh (Ctrl+Shift+R)
3. Проверьте CSP headers

## 📄 License

Proprietary - All rights reserved

---

**Version:** 2.0.0  
**Last Updated:** February 2025  
**Status:** Production Ready ✅
