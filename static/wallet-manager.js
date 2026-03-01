/**
 * SOLDIA v2.0 - Multi-Wallet Integration
 * Support for all major Solana wallets
 */

class WalletManager {
    constructor() {
        this.connected = false;
        this.publicKey = null;
        this.walletType = null;
        
        // Supported wallets
        this.wallets = {
            phantom: {
                name: 'Phantom',
                icon: '👻',
                url: 'https://phantom.app/',
                adapter: null
            },
            solflare: {
                name: 'Solflare',
                icon: '🌞',
                url: 'https://solflare.com/',
                adapter: null
            },
            backpack: {
                name: 'Backpack',
                icon: '🎒',
                url: 'https://backpack.app/',
                adapter: null
            },
            glow: {
                name: 'Glow',
                icon: '✨',
                url: 'https://glow.app/',
                adapter: null
            },
            slope: {
                name: 'Slope',
                icon: '📐',
                url: 'https://slope.finance/',
                adapter: null
            },
            sollet: {
                name: 'Sollet',
                icon: '💼',
                url: 'https://www.sollet.io/',
                adapter: null
            },
            coin98: {
                name: 'Coin98',
                icon: '🪙',
                url: 'https://coin98.com/',
                adapter: null
            },
            exodus: {
                name: 'Exodus',
                icon: '🚀',
                url: 'https://www.exodus.com/',
                adapter: null
            },
            trustwallet: {
                name: 'Trust Wallet',
                icon: '🛡️',
                url: 'https://trustwallet.com/',
                adapter: null
            },
            ledger: {
                name: 'Ledger',
                icon: '🔐',
                url: 'https://www.ledger.com/',
                adapter: null
            }
        };
    }
    
    /**
     * Detect all available wallets
     */
    detectWallets() {
        const available = {};
        
        // Phantom
        if (window.solana && window.solana.isPhantom) {
            available.phantom = this.wallets.phantom;
            this.wallets.phantom.adapter = window.solana;
        }
        
        // Solflare
        if (window.solflare && window.solflare.isSolflare) {
            available.solflare = this.wallets.solflare;
            this.wallets.solflare.adapter = window.solflare;
        }
        
        // Backpack
        if (window.backpack && window.backpack.isBackpack) {
            available.backpack = this.wallets.backpack;
            this.wallets.backpack.adapter = window.backpack;
        }
        
        // Glow
        if (window.glow) {
            available.glow = this.wallets.glow;
            this.wallets.glow.adapter = window.glow;
        }
        
        // Slope
        if (window.Slope) {
            available.slope = this.wallets.slope;
            this.wallets.slope.adapter = new window.Slope();
        }
        
        // Sollet
        if (window.sollet) {
            available.sollet = this.wallets.sollet;
            this.wallets.sollet.adapter = window.sollet;
        }
        
        // Coin98
        if (window.coin98 && window.coin98.sol) {
            available.coin98 = this.wallets.coin98;
            this.wallets.coin98.adapter = window.coin98.sol;
        }
        
        // Exodus
        if (window.exodus && window.exodus.solana) {
            available.exodus = this.wallets.exodus;
            this.wallets.exodus.adapter = window.exodus.solana;
        }
        
        // Trust Wallet
        if (window.trustwallet && window.trustwallet.solana) {
            available.trustwallet = this.wallets.trustwallet;
            this.wallets.trustwallet.adapter = window.trustwallet.solana;
        }
        
        return available;
    }
    
    /**
     * Connect to specific wallet
     */
    async connect(walletType) {
        try {
            const wallet = this.wallets[walletType];
            
            if (!wallet || !wallet.adapter) {
                throw new Error(`${wallet.name} wallet not detected. Please install it first.`);
            }
            
            // Connect based on wallet type
            let response;
            
            if (walletType === 'slope') {
                response = await wallet.adapter.connect();
                this.publicKey = response.data.publicKey;
            } else if (walletType === 'ledger') {
                // Ledger requires special handling
                throw new Error('Ledger support requires additional setup. Please use Ledger Live.');
            } else {
                // Standard Solana wallet adapter protocol
                response = await wallet.adapter.connect();
                this.publicKey = wallet.adapter.publicKey.toString();
            }
            
            this.connected = true;
            this.walletType = walletType;
            
            console.log(`✅ Connected to ${wallet.name}:`, this.publicKey);
            
            // Listen for disconnect
            this.setupDisconnectListener(wallet.adapter);
            
            return {
                success: true,
                publicKey: this.publicKey,
                walletType: walletType,
                walletName: wallet.name
            };
            
        } catch (error) {
            console.error('Wallet connection error:', error);
            throw error;
        }
    }
    
    /**
     * Disconnect wallet
     */
    async disconnect() {
        try {
            if (this.walletType && this.wallets[this.walletType].adapter) {
                await this.wallets[this.walletType].adapter.disconnect();
            }
            
            this.connected = false;
            this.publicKey = null;
            this.walletType = null;
            
            console.log('✅ Wallet disconnected');
            
            return { success: true };
            
        } catch (error) {
            console.error('Disconnect error:', error);
            throw error;
        }
    }
    
    /**
     * Sign transaction
     */
    async signTransaction(transaction) {
        if (!this.connected) {
            throw new Error('Wallet not connected');
        }
        
        try {
            const wallet = this.wallets[this.walletType];
            
            if (this.walletType === 'slope') {
                const { msg, data } = await wallet.adapter.signTransaction(
                    transaction.serialize().toString('base64')
                );
                
                if (msg !== 'ok') {
                    throw new Error('Transaction rejected');
                }
                
                return data;
            } else {
                const signed = await wallet.adapter.signTransaction(transaction);
                return signed;
            }
            
        } catch (error) {
            console.error('Transaction signing error:', error);
            throw error;
        }
    }
    
    /**
     * Sign and send transaction
     */
    async signAndSendTransaction(transaction) {
        if (!this.connected) {
            throw new Error('Wallet not connected');
        }
        
        try {
            const wallet = this.wallets[this.walletType];
            
            if (wallet.adapter.signAndSendTransaction) {
                const signature = await wallet.adapter.signAndSendTransaction(transaction);
                return signature;
            } else {
                // Fallback: sign then send manually
                const signed = await this.signTransaction(transaction);
                // You'll need to send this to Solana RPC
                return signed;
            }
            
        } catch (error) {
            console.error('Send transaction error:', error);
            throw error;
        }
    }
    
    /**
     * Setup disconnect listener
     */
    setupDisconnectListener(adapter) {
        if (adapter.on) {
            adapter.on('disconnect', () => {
                console.log('Wallet disconnected');
                this.connected = false;
                this.publicKey = null;
                this.walletType = null;
                
                // Trigger UI update
                if (window.onWalletDisconnect) {
                    window.onWalletDisconnect();
                }
            });
            
            adapter.on('accountChanged', (publicKey) => {
                if (publicKey) {
                    console.log('Account changed:', publicKey.toString());
                    this.publicKey = publicKey.toString();
                    
                    // Trigger UI update
                    if (window.onAccountChanged) {
                        window.onAccountChanged(this.publicKey);
                    }
                } else {
                    this.disconnect();
                }
            });
        }
    }
    
    /**
     * Get wallet balance
     */
    async getBalance() {
        if (!this.connected) {
            throw new Error('Wallet not connected');
        }
        
        try {
            // This requires Solana Web3.js
            // Implementation depends on your setup
            return null;
        } catch (error) {
            console.error('Get balance error:', error);
            throw error;
        }
    }
    
    /**
     * Get installed wallets count
     */
    getInstalledCount() {
        const available = this.detectWallets();
        return Object.keys(available).length;
    }
    
    /**
     * Show wallet selection modal
     */
    showWalletModal() {
        const available = this.detectWallets();
        const count = Object.keys(available).length;
        
        if (count === 0) {
            return this.showNoWalletsModal();
        }
        
        if (count === 1) {
            // Auto-connect to the only available wallet
            const walletType = Object.keys(available)[0];
            return this.connect(walletType);
        }
        
        // Show selection modal
        return this.createWalletSelectionModal(available);
    }
    
    /**
     * Create wallet selection modal
     */
    createWalletSelectionModal(available) {
        return new Promise((resolve, reject) => {
            const modal = document.createElement('div');
            modal.className = 'wallet-modal';
            modal.innerHTML = `
                <div class="wallet-modal-overlay"></div>
                <div class="wallet-modal-content">
                    <div class="wallet-modal-header">
                        <h2>Connect Wallet</h2>
                        <button class="wallet-modal-close">&times;</button>
                    </div>
                    <div class="wallet-modal-body">
                        <p class="wallet-modal-subtitle">Select your Solana wallet</p>
                        <div class="wallet-list">
                            ${Object.entries(available).map(([type, wallet]) => `
                                <button class="wallet-option" data-wallet="${type}">
                                    <span class="wallet-icon">${wallet.icon}</span>
                                    <span class="wallet-name">${wallet.name}</span>
                                    <span class="wallet-status">Detected</span>
                                </button>
                            `).join('')}
                        </div>
                        <hr>
                        <div class="wallet-list">
                            <p class="wallet-modal-subtitle">Not installed</p>
                            ${Object.entries(this.wallets)
                                .filter(([type]) => !available[type])
                                .map(([type, wallet]) => `
                                <a href="${wallet.url}" target="_blank" class="wallet-option wallet-option-install">
                                    <span class="wallet-icon">${wallet.icon}</span>
                                    <span class="wallet-name">${wallet.name}</span>
                                    <span class="wallet-status">Install</span>
                                </a>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // Add styles
            this.addModalStyles();
            
            // Event listeners
            const closeModal = () => {
                document.body.removeChild(modal);
                reject(new Error('User cancelled'));
            };
            
            modal.querySelector('.wallet-modal-close').addEventListener('click', closeModal);
            modal.querySelector('.wallet-modal-overlay').addEventListener('click', closeModal);
            
            modal.querySelectorAll('.wallet-option[data-wallet]').forEach(button => {
                button.addEventListener('click', async () => {
                    const walletType = button.dataset.wallet;
                    try {
                        const result = await this.connect(walletType);
                        document.body.removeChild(modal);
                        resolve(result);
                    } catch (error) {
                        alert(`Failed to connect: ${error.message}`);
                    }
                });
            });
        });
    }
    
    /**
     * Show "no wallets installed" modal
     */
    showNoWalletsModal() {
        const modal = document.createElement('div');
        modal.className = 'wallet-modal';
        modal.innerHTML = `
            <div class="wallet-modal-overlay"></div>
            <div class="wallet-modal-content">
                <div class="wallet-modal-header">
                    <h2>No Wallet Detected</h2>
                    <button class="wallet-modal-close">&times;</button>
                </div>
                <div class="wallet-modal-body">
                    <p style="text-align: center; margin: 20px 0;">
                        Please install a Solana wallet to continue:
                    </p>
                    <div class="wallet-list">
                        ${Object.entries(this.wallets).slice(0, 5).map(([type, wallet]) => `
                            <a href="${wallet.url}" target="_blank" class="wallet-option wallet-option-install">
                                <span class="wallet-icon">${wallet.icon}</span>
                                <span class="wallet-name">${wallet.name}</span>
                                <span class="wallet-status">Install</span>
                            </a>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        this.addModalStyles();
        
        const closeModal = () => document.body.removeChild(modal);
        modal.querySelector('.wallet-modal-close').addEventListener('click', closeModal);
        modal.querySelector('.wallet-modal-overlay').addEventListener('click', closeModal);
    }
    
    /**
     * Add modal styles
     */
    addModalStyles() {
        if (document.getElementById('wallet-modal-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'wallet-modal-styles';
        styles.textContent = `
            .wallet-modal {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 10000;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .wallet-modal-overlay {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.8);
                backdrop-filter: blur(10px);
            }
            
            .wallet-modal-content {
                position: relative;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                border-radius: 20px;
                max-width: 500px;
                width: 90%;
                max-height: 80vh;
                overflow: hidden;
                box-shadow: 0 20px 60px rgba(0, 240, 255, 0.3);
                border: 1px solid rgba(0, 240, 255, 0.2);
            }
            
            .wallet-modal-header {
                padding: 25px 30px;
                border-bottom: 1px solid rgba(0, 240, 255, 0.1);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .wallet-modal-header h2 {
                margin: 0;
                color: #00F0FF;
                font-size: 24px;
                font-weight: 700;
            }
            
            .wallet-modal-close {
                background: none;
                border: none;
                color: #fff;
                font-size: 32px;
                cursor: pointer;
                padding: 0;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0.6;
                transition: opacity 0.3s;
            }
            
            .wallet-modal-close:hover {
                opacity: 1;
            }
            
            .wallet-modal-body {
                padding: 20px 30px 30px;
                max-height: calc(80vh - 100px);
                overflow-y: auto;
            }
            
            .wallet-modal-subtitle {
                color: rgba(255, 255, 255, 0.6);
                font-size: 14px;
                margin: 0 0 15px 0;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .wallet-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-bottom: 20px;
            }
            
            .wallet-option {
                display: flex;
                align-items: center;
                padding: 15px 20px;
                background: rgba(0, 240, 255, 0.05);
                border: 1px solid rgba(0, 240, 255, 0.2);
                border-radius: 12px;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                color: white;
            }
            
            .wallet-option:hover {
                background: rgba(0, 240, 255, 0.1);
                border-color: rgba(0, 240, 255, 0.4);
                transform: translateY(-2px);
            }
            
            .wallet-icon {
                font-size: 28px;
                margin-right: 15px;
            }
            
            .wallet-name {
                flex: 1;
                font-size: 16px;
                font-weight: 600;
            }
            
            .wallet-status {
                font-size: 12px;
                padding: 4px 12px;
                background: rgba(0, 240, 255, 0.2);
                border-radius: 20px;
                color: #00F0FF;
            }
            
            .wallet-option-install .wallet-status {
                background: rgba(255, 16, 240, 0.2);
                color: #FF10F0;
            }
            
            hr {
                border: none;
                border-top: 1px solid rgba(0, 240, 255, 0.1);
                margin: 20px 0;
            }
        `;
        
        document.head.appendChild(styles);
    }
}

// Create global instance
const walletManager = new WalletManager();

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WalletManager, walletManager };
}

console.log('✅ Multi-Wallet Manager loaded - Supports 10 wallets!');
