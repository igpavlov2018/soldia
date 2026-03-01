/**
 * SOLDIA v2.0 - API Configuration
 * This file should be included BEFORE the main app scripts
 */

// API Configuration
const API_CONFIG = {
    // Base API URL
    baseUrl: window.location.origin,
    
    // API Endpoints
    endpoints: {
        // Health
        health: '/health',
        healthDetailed: '/health/detailed',
        
        // Users
        register: '/api/users/register',
        getUserStats: (wallet) => `/api/users/stats/${wallet}`,
        getDetailedStats: (wallet) => `/api/users/stats/detailed/${wallet}`,
        getUserHistory: (wallet) => `/api/users/history/${wallet}`,
        
        // Deposits
        verifyDeposit: '/api/deposits/verify',
        
        // Withdrawals
        requestWithdrawal: '/api/withdrawals/withdraw',
        getWithdrawalStats: (wallet) => `/api/withdrawals/stats?wallet_address=${wallet}`,
        
        // Referrals
        getReferralTree: (wallet) => `/api/referrals/tree/${wallet}`,
        getReferralStats: (wallet) => `/api/referrals/stats/${wallet}`
    },
    
    // Settings
    settings: {
        // Request timeout (ms)
        timeout: 30000,
        
        // Retry failed requests
        retryAttempts: 3,
        
        // Cache TTL (ms)
        cacheTTL: 60000
    }
};

// API Helper Functions
const API = {
    /**
     * Make API request with error handling
     */
    async request(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };
        
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), API_CONFIG.settings.timeout);
            
            const response = await fetch(url, {
                ...defaultOptions,
                signal: controller.signal
            });
            
            clearTimeout(timeout);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            return data;
            
        } catch (error) {
            console.error('API Request Error:', error);
            throw error;
        }
    },
    
    /**
     * GET request
     */
    async get(endpoint) {
        const url = API_CONFIG.baseUrl + endpoint;
        return await this.request(url, { method: 'GET' });
    },
    
    /**
     * POST request
     */
    async post(endpoint, data) {
        const url = API_CONFIG.baseUrl + endpoint;
        return await this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },
    
    /**
     * Health check
     */
    async healthCheck() {
        return await this.get(API_CONFIG.endpoints.health);
    },
    
    /**
     * Get configuration
     */
    async getConfig() {
        return await this.get(API_CONFIG.endpoints.config);
    },
    
    /**
     * Register user
     */
    async register(walletAddress, referralCode = null, telegramId = null) {
        return await this.post(API_CONFIG.endpoints.register, {
            wallet_address: walletAddress,
            referral_code: referralCode,
            telegram_id: telegramId
        });
    },
    
    /**
     * Get user statistics
     */
    async getUserStats(walletAddress) {
        const endpoint = API_CONFIG.endpoints.getUserStats(walletAddress);
        return await this.get(endpoint);
    },
    
    /**
     * Get detailed statistics
     */
    async getDetailedStats(walletAddress) {
        const endpoint = API_CONFIG.endpoints.getDetailedStats(walletAddress);
        return await this.get(endpoint);
    },
    
    /**
     * Verify deposit
     */
    async verifyDeposit(walletAddress, txHash, amount) {
        return await this.post(API_CONFIG.endpoints.verifyDeposit, {
            wallet_address: walletAddress,
            tx_hash: txHash,
            amount: amount.toString()
        });
    },
    
    /**
     * Request withdrawal (requires signature + idempotency key)
     */
    async requestWithdrawal(walletAddress, amount, signature, idempotencyKey) {
        return await this.post(API_CONFIG.endpoints.requestWithdrawal, {
            wallet_address: walletAddress,
            amount: amount.toString(),
            signature: signature,
            idempotency_key: idempotencyKey
        });
    },
    
    /**
     * Get withdrawal stats
     */
    async getWithdrawalStats(walletAddress) {
        const endpoint = API_CONFIG.endpoints.getWithdrawalStats(walletAddress);
        return await this.get(endpoint);
    },

    /**
     * Get referral tree
     */
    async getReferralTree(walletAddress) {
        const endpoint = API_CONFIG.endpoints.getReferralTree(walletAddress);
        return await this.get(endpoint);
    },

    /**
     * Get referral stats
     */
    async getReferralStats(walletAddress) {
        const endpoint = API_CONFIG.endpoints.getReferralStats(walletAddress);
        return await this.get(endpoint);
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { API_CONFIG, API };
}

console.log('✅ SOLDIA API Configuration loaded');
