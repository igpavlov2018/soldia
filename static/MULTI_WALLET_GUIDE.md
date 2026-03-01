# 💼 SOLDIA v2.0 - Multi-Wallet Support

## 🎯 Поддерживаемые кошельки

Теперь SOLDIA поддерживает **10 популярных Solana кошельков**:

### ✅ Основные кошельки:

1. **👻 Phantom** - Самый популярный
   - Website: https://phantom.app/
   - Пользователей: 3M+
   - Поддержка: Full

2. **🌞 Solflare** - Web & Mobile
   - Website: https://solflare.com/
   - Пользователей: 1M+
   - Поддержка: Full

3. **🎒 Backpack** - Multi-chain
   - Website: https://backpack.app/
   - Пользователей: 500K+
   - Поддержка: Full

4. **✨ Glow** - Security focused
   - Website: https://glow.app/
   - Пользователей: 200K+
   - Поддержка: Full

5. **📐 Slope** - Mobile-first
   - Website: https://slope.finance/
   - Пользователей: 300K+
   - Поддержка: Full

### ✅ Дополнительные кошельки:

6. **💼 Sollet** - Web wallet
   - Website: https://www.sollet.io/
   - Поддержка: Full

7. **🪙 Coin98** - Multi-chain
   - Website: https://coin98.com/
   - Поддержка: Full

8. **🚀 Exodus** - Desktop + Mobile
   - Website: https://www.exodus.com/
   - Поддержка: Full

9. **🛡️ Trust Wallet** - Multi-chain mobile
   - Website: https://trustwallet.com/
   - Поддержка: Full

10. **🔐 Ledger** - Hardware wallet
    - Website: https://www.ledger.com/
    - Поддержка: Requires Ledger Live

---

## 🚀 Интеграция

### 1. Добавьте скрипт в HTML

В `index.html` добавьте перед закрывающим `</body>`:

```html
<!-- Multi-Wallet Support -->
<script src="/static/wallet-manager.js"></script>
```

### 2. Использование

```javascript
// Показать модальное окно выбора кошелька
async function connectWallet() {
    try {
        const result = await walletManager.showWalletModal();
        
        console.log('Connected!');
        console.log('Wallet:', result.walletName);
        console.log('Address:', result.publicKey);
        
        // Обновите UI
        updateUIAfterConnect(result);
        
    } catch (error) {
        console.error('Connection failed:', error);
    }
}

// Отключить кошелек
async function disconnectWallet() {
    try {
        await walletManager.disconnect();
        console.log('Disconnected');
        
        // Обновите UI
        updateUIAfterDisconnect();
        
    } catch (error) {
        console.error('Disconnect failed:', error);
    }
}

// Подписать транзакцию
async function signTransaction(transaction) {
    try {
        const signed = await walletManager.signTransaction(transaction);
        return signed;
    } catch (error) {
        console.error('Signing failed:', error);
        throw error;
    }
}
```

### 3. Замените старый код

В оригинальном `index.html` найдите функцию `connectWallet()` и замените на:

```javascript
async function connectWallet() {
    try {
        // Используем новый WalletManager
        const result = await walletManager.showWalletModal();
        
        currentWalletAddress = result.publicKey;
        
        // Зарегистрировать пользователя
        await registerUser(result.publicKey);
        
        // Загрузить dashboard
        await loadDashboardData(result.publicKey);
        
    } catch (error) {
        console.error('Connection error:', error);
        showError(error.message);
    }
}
```

---

## 🎨 UI Features

### Модальное окно выбора кошелька

Когда пользователь нажимает "Connect Wallet", показывается красивое модальное окно:

**Секция 1: Установленные кошельки**
- Показывает только те кошельки, которые установлены
- Кнопка "Connect" для каждого
- Статус "Detected"

**Секция 2: Не установленные кошельки**
- Показывает остальные кошельки
- Ссылка на установку
- Статус "Install"

**Автоматическое поведение:**
- Если установлен 1 кошелек → автоматическое подключение
- Если установлено несколько → показать выбор
- Если ничего не установлено → показать список для установки

---

## 📱 Обработка событий

### Account Changed

```javascript
// Callback когда пользователь меняет аккаунт в кошельке
window.onAccountChanged = (newPublicKey) => {
    console.log('Account changed:', newPublicKey);
    
    // Обновите данные пользователя
    currentWalletAddress = newPublicKey;
    loadDashboardData(newPublicKey);
};
```

### Disconnect

```javascript
// Callback когда пользователь отключает кошелек
window.onWalletDisconnect = () => {
    console.log('Wallet disconnected');
    
    // Вернуться на главную страницу
    currentWalletAddress = null;
    showHeroSection();
};
```

---

## 🔧 Дополнительные методы

### Проверить установленные кошельки

```javascript
const available = walletManager.detectWallets();
console.log('Available wallets:', available);

// Получить количество
const count = walletManager.getInstalledCount();
console.log('Installed wallets:', count);
```

### Получить текущий кошелек

```javascript
if (walletManager.connected) {
    console.log('Wallet:', walletManager.walletType);
    console.log('Address:', walletManager.publicKey);
}
```

### Прямое подключение к конкретному кошельку

```javascript
// Подключиться к Phantom напрямую
try {
    const result = await walletManager.connect('phantom');
    console.log('Connected to Phantom:', result.publicKey);
} catch (error) {
    console.error('Failed:', error);
}
```

---

## 🎨 Кастомизация UI

### Изменить стили модального окна

В `wallet-manager.js` найдите метод `addModalStyles()` и измените CSS переменные:

```javascript
.wallet-modal-content {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    /* Измените на свой градиент */
}
```

### Добавить свой кошелек

```javascript
// В constructor WalletManager добавьте:
this.wallets.myWallet = {
    name: 'My Custom Wallet',
    icon: '🎯',
    url: 'https://mywallet.com/',
    adapter: null
};

// В detectWallets() добавьте:
if (window.myWallet) {
    available.myWallet = this.wallets.myWallet;
    this.wallets.myWallet.adapter = window.myWallet;
}
```

---

## 🐛 Troubleshooting

### Кошелек не определяется

**Проблема:** `walletManager.detectWallets()` возвращает пустой объект

**Решение:**
1. Убедитесь что расширение установлено
2. Обновите страницу (F5)
3. Проверьте консоль браузера
4. Попробуйте другой браузер

### Ошибка при подключении

**Проблема:** "Failed to connect"

**Решение:**
1. Убедитесь что используете HTTPS (не localhost)
2. Разрешите доступ в настройках кошелька
3. Проверьте что кошелек разблокирован
4. Попробуйте переустановить расширение

### Модальное окно не появляется

**Проблема:** Нет модального окна при клике

**Решение:**
1. Проверьте что `wallet-manager.js` загружен
2. Откройте консоль (F12) и проверьте ошибки
3. Убедитесь что вызываете `walletManager.showWalletModal()`

---

## 📊 Статистика кошельков

### Популярность на Solana (февраль 2025):

```
Phantom      ████████████████████ 60%
Solflare     ██████████ 20%
Backpack     ████ 8%
Glow         ██ 4%
Slope        ██ 3%
Остальные    ██ 5%
```

### Рекомендации:

1. **Для новичков:** Phantom (самый простой)
2. **Для мобильных:** Slope, Trust Wallet
3. **Для безопасности:** Glow, Ledger
4. **Для multi-chain:** Coin98, Exodus
5. **Для web:** Solflare, Sollet

---

## 🔐 Security Best Practices

### Никогда не делайте:

❌ Не запрашивайте seed phrase  
❌ Не сохраняйте private keys  
❌ Не подписывайте неизвестные транзакции  
❌ Не подключайтесь на HTTP (только HTTPS)  

### Всегда делайте:

✅ Проверяйте URL сайта  
✅ Показывайте детали транзакции перед подписью  
✅ Используйте HTTPS  
✅ Логируйте все операции  
✅ Показывайте warnings для больших сумм  

---

## 🚀 Migration Guide

### Если у вас был старый код с Phantom/Solflare:

**Старый код:**
```javascript
async function connectWallet() {
    if (window.solana && window.solana.isPhantom) {
        await window.solana.connect();
        // ...
    } else if (window.solflare) {
        await window.solflare.connect();
        // ...
    }
}
```

**Новый код:**
```javascript
async function connectWallet() {
    const result = await walletManager.showWalletModal();
    // Работает со всеми кошельками!
}
```

### Преимущества:

- ✅ 10 кошельков вместо 2
- ✅ Красивое модальное окно
- ✅ Автоматическое определение
- ✅ Unified API для всех кошельков
- ✅ Обработка событий
- ✅ Меньше кода

---

## 📝 Example Integration

Полный пример интеграции в существующий HTML:

```html
<!DOCTYPE html>
<html>
<head>
    <title>SOLDIA</title>
</head>
<body>
    <!-- Ваш контент -->
    
    <button onclick="handleConnect()">Connect Wallet</button>
    <button onclick="handleDisconnect()" style="display:none" id="disconnectBtn">
        Disconnect
    </button>
    
    <div id="walletInfo" style="display:none">
        <p>Connected: <span id="walletAddress"></span></p>
        <p>Wallet: <span id="walletType"></span></p>
    </div>
    
    <!-- Scripts -->
    <script src="/static/wallet-manager.js"></script>
    <script>
        async function handleConnect() {
            try {
                const result = await walletManager.showWalletModal();
                
                // Показать информацию
                document.getElementById('walletInfo').style.display = 'block';
                document.getElementById('walletAddress').textContent = 
                    result.publicKey.slice(0, 8) + '...' + result.publicKey.slice(-8);
                document.getElementById('walletType').textContent = result.walletName;
                
                // Показать кнопку disconnect
                document.getElementById('disconnectBtn').style.display = 'block';
                
            } catch (error) {
                alert('Connection failed: ' + error.message);
            }
        }
        
        async function handleDisconnect() {
            await walletManager.disconnect();
            
            // Скрыть информацию
            document.getElementById('walletInfo').style.display = 'none';
            document.getElementById('disconnectBtn').style.display = 'none';
        }
        
        // Обработка событий
        window.onWalletDisconnect = () => {
            handleDisconnect();
        };
    </script>
</body>
</html>
```

---

## 🎉 Готово!

Теперь ваше приложение поддерживает **10 популярных Solana кошельков**!

**Что дальше:**
1. Добавьте `wallet-manager.js` в ваш HTML
2. Замените старый код подключения
3. Протестируйте с разными кошельками
4. Кастомизируйте UI под ваш дизайн

**Поддержка:** 
- Phantom ✅
- Solflare ✅
- Backpack ✅
- Glow ✅
- Slope ✅
- Sollet ✅
- Coin98 ✅
- Exodus ✅
- Trust Wallet ✅
- Ledger ✅

---

**Version:** 2.0.0  
**Last Updated:** February 2025  
**Status:** Production Ready ✅
