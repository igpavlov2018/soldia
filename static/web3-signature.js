/**
 * SOLDIA v2.0 - Web3 Signature Module
 * Handles wallet message signing for authentication
 * PRODUCTION-READY
 */

class SolanaSignatureManager {
    constructor(walletManager) {
        this.walletManager = walletManager;
        this.logger = console;
    }

    /**
     * Sign a message with the connected wallet
     * Uses Ed25519 signature scheme (Solana standard)
     * 
     * @param {string} message - Message to sign
     * @returns {Promise<string>} - Base58-encoded signature
     */
    async signMessage(message) {
        try {
            if (!this.walletManager.userWallet) {
                throw new Error('No wallet connected. Please connect wallet first.');
            }

            const messageBuffer = new TextEncoder().encode(message);
            
            // Get the current wallet adapter
            const walletType = this.walletManager.walletType;
            if (!walletType) {
                throw new Error('No wallet type selected');
            }

            const adapter = this.walletManager.wallets[walletType]?.adapter;
            if (!adapter) {
                throw new Error(`Wallet adapter for ${walletType} not found`);
            }

            // Check if wallet supports message signing
            if (!adapter.signMessage) {
                throw new Error(`Wallet ${walletType} does not support message signing`);
            }

            // Sign the message
            this.logger.log(`[Web3] Signing message with ${walletType}...`);
            const signedMessage = await adapter.signMessage(messageBuffer);
            
            // Convert signature to Base58
            // signedMessage.signature is Uint8Array
            const signatureArray = signedMessage.signature;
            const signature = window.bs58?.encode(signatureArray);
            
            if (!signature) {
                throw new Error('Failed to encode signature');
            }

            this.logger.log(`[Web3] ✓ Message signed successfully`);
            this.logger.log(`[Web3] Signature: ${signature.substring(0, 20)}...`);

            return signature;

        } catch (error) {
            this.logger.error('[Web3] Signature error:', error);
            throw new Error(`Failed to sign message: ${error.message}`);
        }
    }

    /**
     * Construct and sign a withdrawal request
     * 
     * @param {number} amount - USDC amount to withdraw
     * @param {string} destinationWallet - Destination wallet address
     * @returns {Promise<Object>} - { message, signature }
     */
    async signWithdrawalRequest(amount, destinationWallet) {
        try {
            const message = `Withdraw ${parseFloat(amount).toFixed(2)} USDC to ${destinationWallet}`;
            this.logger.log(`[Web3] Withdrawal message: "${message}"`);

            const signature = await this.signMessage(message);

            return {
                message,
                signature,
                walletAddress: this.walletManager.userWallet
            };

        } catch (error) {
            this.logger.error('[Web3] Withdrawal signing error:', error);
            throw error;
        }
    }

    /**
     * Construct and sign a deposit confirmation
     * 
     * @param {string} txHash - Transaction signature
     * @param {number} amount - USDC amount
     * @returns {Promise<Object>} - { message, signature }
     */
    async signDepositConfirmation(txHash, amount) {
        try {
            const message = `Confirm deposit ${txHash} for ${parseFloat(amount).toFixed(2)} USDC`;
            this.logger.log(`[Web3] Deposit message: "${message}"`);

            const signature = await this.signMessage(message);

            return {
                message,
                signature,
                walletAddress: this.walletManager.userWallet
            };

        } catch (error) {
            this.logger.error('[Web3] Deposit signing error:', error);
            throw error;
        }
    }

    /**
     * Verify that a signature is valid format
     * (Does NOT verify cryptographic validity - that's done server-side)
     * 
     * @param {string} signature - Base58-encoded signature
     * @returns {boolean} - True if signature format is valid
     */
    isValidSignatureFormat(signature) {
        if (!signature || typeof signature !== 'string') {
            return false;
        }
        
        // Solana signatures are Base58 encoded, typically 88-90 characters
        // But we allow some variance
        return signature.length >= 80 && signature.length <= 150;
    }

    /**
     * Verify message hash (client-side verification for debugging)
     * Note: Real verification happens on server with actual public key
     * 
     * @param {string} message - Original message
     * @param {string} signature - Base58 signature
     * @returns {boolean} - Format validation only
     */
    verifySignatureFormat(message, signature) {
        if (!message || !signature) {
            this.logger.error('[Web3] Missing message or signature');
            return false;
        }

        if (!this.isValidSignatureFormat(signature)) {
            this.logger.error('[Web3] Invalid signature format');
            return false;
        }

        this.logger.log('[Web3] Signature format is valid');
        return true;
    }
}

/**
 * Initialize the signature manager
 * Should be called after wallet manager is created
 */
function initSignatureManager() {
    // Wait for wallet manager to be ready
    if (typeof window.walletManager === 'undefined') {
        console.warn('[Web3] Wallet manager not found, retrying in 100ms...');
        setTimeout(initSignatureManager, 100);
        return;
    }

    window.signatureManager = new SolanaSignatureManager(window.walletManager);
    console.log('[Web3] ✓ Signature manager initialized');
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSignatureManager);
} else {
    initSignatureManager();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SolanaSignatureManager;
}
