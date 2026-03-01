"""
✅ FIXED v2.9: Solana Blockchain Client

ИСПРАВЛЕНИЯ v2.9:
  CRIT-A: Transaction.sign([keypair]) → Transaction.sign([keypair], recent_blockhash)
           В solders 0.19 метод sign() ТРЕБУЕТ recent_blockhash как второй аргумент.
           Установка tx.recent_blockhash как атрибута и вызов sign() без blockhash
           вызывает TypeError в runtime.

  CRIT-C: spl.token импорты заменены — SPL TransferChecked инструкция строится
           вручную через solders primitives (Instruction, AccountMeta, struct.pack).
           spl-token==0.2.0 несовместим с solders 0.19 (несовпадение типов Pubkey).

  WARN-4: confirm_transaction() — solana-py 0.32 возвращает RpcResponse[SignatureStatuses].
           .value — это list[Optional[TransactionStatus]]. Проверка if confirm_resp.value:
           всегда True (непустой список). Исправлено: проверяем value[0] is not None
           и value[0].err is None.

  WARN-5: Добавлен timeout=30 к AsyncClient — предотвращает зависание при недоступности RPC.

  API-FIX: get_token_accounts_by_owner принимает TokenAccountOpts, не dict.
           В solana-py 0.32 второй аргумент — TokenAccountOpts (solana.rpc.types).

Все остальные части (verify_transaction, verify_usdc_transaction, get_usdc_balance)
сохранены с минимальными исправлениями только там где нужно.
"""

import logging
import struct
from decimal import Decimal
from typing import Optional
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey
from solders.signature import Signature
from config.settings import settings, constants

logger = logging.getLogger(__name__)


# ==================== USDC CONVERSION HELPERS ====================

def lamports_to_usdc(lamports: int) -> Decimal:
    """Convert USDC lamports to human-readable USDC (6 decimals)"""
    return Decimal(lamports) / Decimal(10 ** constants.USDC_DECIMALS)


def usdc_to_lamports(usdc: Decimal) -> int:
    """Convert human-readable USDC to lamports"""
    return int(usdc * Decimal(10 ** constants.USDC_DECIMALS))


# ==================== SPL TOKEN INSTRUCTION BUILDER ====================

def _build_transfer_checked_instruction(
    source: Pubkey,
    mint: Pubkey,
    dest: Pubkey,
    owner: Pubkey,
    amount: int,
    decimals: int,
):
    """
    CRIT-C FIX: Build SPL Token TransferChecked instruction manually using solders primitives.

    spl-token==0.2.0 is incompatible with solders==0.19.0 — Pubkey types do not match,
    causing TypeError at import or call time. We build the instruction directly using the
    SPL Token program ABI without depending on the spl-token package at all.

    SPL Token program ID: TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
    TransferChecked instruction layout (little-endian):
      - u8:  instruction index = 12
      - u64: amount
      - u8:  decimals

    Accounts (in order):
      0. source  — writable, not signer
      1. mint    — read-only, not signer
      2. dest    — writable, not signer
      3. owner   — signer
    """
    from solders.instruction import Instruction, AccountMeta

    SPL_TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

    # Borsh-encode: u8(12) + u64(amount, LE) + u8(decimals)
    data = struct.pack("<BQB", 12, amount, decimals)

    accounts = [
        AccountMeta(pubkey=source, is_signer=False, is_writable=True),
        AccountMeta(pubkey=mint,   is_signer=False, is_writable=False),
        AccountMeta(pubkey=dest,   is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner,  is_signer=True,  is_writable=False),
    ]

    return Instruction(
        program_id=SPL_TOKEN_PROGRAM_ID,
        accounts=accounts,
        data=bytes(data),
    )


# ==================== SOLANA CLIENT ====================

class SolanaClient:
    """
    ✅ FIXED v2.9: Solana blockchain client — correct solana-py 0.32 + solders 0.19 API.

    Key fixes:
    - Transaction.sign([keypair], recent_blockhash) — CRIT-A
    - Manual SPL TransferChecked instruction — CRIT-C
    - Correct confirm_transaction() parsing — WARN-4
    - RPC timeout=30s — WARN-5
    - TokenAccountOpts instead of dict — API-FIX
    - Multi-transfer attack detection (preserved)
    - AWS KMS support (preserved)
    """

    def __init__(self):
        self.rpc_url = settings.SOLANA_RPC
        self.usdc_mint = Pubkey.from_string(settings.USDC_MINT)
        self.client: Optional[AsyncClient] = None

    async def connect(self):
        """Initialize connection to Solana RPC with timeout"""
        if not self.client:
            # WARN-5 FIX: timeout=30 prevents indefinite hangs when mainnet RPC is slow
            self.client = AsyncClient(self.rpc_url, timeout=30)
            logger.info(f"🌐 Connected to Solana RPC: {self.rpc_url}")

    async def close(self):
        """Close RPC connection"""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("🌐 Solana RPC connection closed")

    async def verify_transaction(self, signature: str) -> Optional[dict]:
        """Verify transaction on Solana blockchain"""
        try:
            await self.connect()

            sig = Signature.from_string(signature)
            response = await self.client.get_transaction(
                sig,
                encoding="jsonParsed",
                commitment=Confirmed,
                max_supported_transaction_version=0
            )

            if not response.value:
                logger.warning(f"Transaction not found: {signature}")
                return None

            tx = response.value

            # Check if transaction has errors
            has_error = tx.transaction.meta and tx.transaction.meta.err is not None

            # Extract basic info
            result = {
                "signature": signature,
                "confirmed": not has_error,
                "slot": tx.slot,
                "block_time": tx.block_time if hasattr(tx, 'block_time') else None,
                "error": str(tx.transaction.meta.err) if has_error else None
            }

            # Try to extract transfer info if present
            try:
                instructions = tx.transaction.transaction.message.instructions
                for instruction in instructions:
                    if hasattr(instruction, 'parsed'):
                        parsed = instruction.parsed
                        if isinstance(parsed, dict):
                            info = parsed.get('info', {})
                            if parsed.get('type') in ['transfer', 'transferChecked']:
                                result['transfer_type'] = parsed.get('type')
                                result['mint'] = info.get('mint')
                                result['destination'] = info.get('destination')
                                result['source'] = info.get('source') or info.get('authority')

                                if 'tokenAmount' in info:
                                    result['amount'] = Decimal(info['tokenAmount'].get('uiAmountString', '0'))
                                elif 'amount' in info:
                                    result['amount_raw'] = info['amount']
                                break
            except Exception as parse_error:
                logger.debug(f"Could not parse transfer details: {parse_error}")

            logger.info(f"✅ Transaction verified: {signature}")
            return result

        except Exception as e:
            logger.error(f"Error verifying transaction: {e}")
            return None

    async def get_usdc_balance(self, wallet: str) -> Decimal:
        """Get USDC balance for wallet"""
        try:
            await self.connect()

            wallet_pubkey = Pubkey.from_string(wallet)

            # API-FIX: TokenAccountOpts (not dict) for solana-py 0.32
            token_accounts_resp = await self.client.get_token_accounts_by_owner(
                wallet_pubkey,
                TokenAccountOpts(mint=self.usdc_mint),
                encoding="jsonParsed"
            )

            if not token_accounts_resp.value or len(token_accounts_resp.value) == 0:
                logger.warning(f"No USDC token account found for {wallet}")
                return Decimal("0")

            # Get balance from first token account
            balance_data = token_accounts_resp.value[0].account.data.parsed["info"]["tokenAmount"]
            balance = Decimal(balance_data["uiAmountString"])

            logger.info(f"USDC Balance for {wallet}: {balance}")
            return balance

        except Exception as e:
            logger.error(f"Error getting USDC balance: {e}")
            return Decimal("0")

    async def get_sol_balance(self, wallet: str) -> Decimal:
        """
        Get native SOL balance for wallet.

        Used to verify the hot wallet has enough SOL to pay Solana transaction fees.
        Each SPL token transfer (including USDC) costs ~0.000005 SOL in network fees.
        The fee is always paid in SOL regardless of which token is being transferred.

        Returns SOL balance as Decimal (e.g. Decimal("0.05") = 0.05 SOL).
        Returns Decimal("0") on any error — caller must treat this as a warning.
        """
        try:
            await self.connect()
            pubkey = Pubkey.from_string(wallet)
            resp = await self.client.get_balance(pubkey)
            if resp.value is None:
                return Decimal("0")
            # Solana reports lamports (1 SOL = 1_000_000_000 lamports)
            return Decimal(resp.value) / Decimal("1000000000")
        except Exception as e:
            logger.error(f"Error getting SOL balance for {wallet}: {e}")
            return Decimal("0")

    async def send_usdc(
        self,
        to_wallet: str,
        amount: Decimal,
        private_key: Optional[str] = None
    ) -> Optional[str]:
        """
        Send USDC to wallet.

        CRIT-A FIX: tx.sign([keypair], recent_blockhash) — blockhash is required
          as the second argument to sign() in solders 0.19.

        CRIT-C FIX: SPL TransferChecked instruction built manually via solders
          primitives. No spl-token package dependency.

        WARN-4 FIX: confirm_transaction() result parsed correctly.

        API-FIX: TokenAccountOpts instead of dict.

        Supports AWS KMS for secure key management.
        """
        try:
            await self.connect()

            logger.info(f"💸 Sending {amount} USDC to {to_wallet}")

            from solders.keypair import Keypair
            from solders.transaction import Transaction as SoldersTransaction

            # 1. Parse private key
            if not private_key:
                try:
                    from security.key_management import get_key_manager
                    key_manager = get_key_manager(
                        aws_region=getattr(settings, 'AWS_REGION', 'us-east-1'),
                        kms_key_id=getattr(settings, 'KMS_KEY_ID', None)
                    )
                    private_key = await key_manager.get_private_key()
                    logger.info("✅ Using private key from AWS KMS")
                except Exception as e:
                    logger.warning(f"AWS KMS not available, falling back to environment: {e}")
                    private_key = settings.HOT_WALLET_PRIVATE_KEY

            if not private_key:
                raise ValueError("Private key not provided and HOT_WALLET_PRIVATE_KEY not set")

            try:
                keypair = Keypair.from_base58_string(private_key)
            except Exception as e:
                logger.error(f"Failed to parse private key: {e}")
                raise ValueError(f"Invalid private key format: {e}")

            actual_from_wallet = str(keypair.pubkey())
            logger.info(f"Using wallet: {actual_from_wallet}")

            # 2. Get source token account
            # API-FIX: TokenAccountOpts instead of dict
            from_token_resp = await self.client.get_token_accounts_by_owner(
                keypair.pubkey(),
                TokenAccountOpts(mint=self.usdc_mint),
                encoding="jsonParsed"
            )

            if not from_token_resp.value or len(from_token_resp.value) == 0:
                raise ValueError(f"Source token account not found for wallet {actual_from_wallet}")

            from_token_account = Pubkey.from_string(str(from_token_resp.value[0].pubkey))

            # Check balance
            from_balance_data = from_token_resp.value[0].account.data.parsed["info"]["tokenAmount"]
            from_balance = Decimal(from_balance_data["uiAmountString"])
            logger.info(f"Source wallet balance: {from_balance} USDC")

            if from_balance < amount:
                raise ValueError(f"Insufficient balance: {from_balance} USDC, need {amount} USDC")

            # 3. Get destination token account
            to_pubkey = Pubkey.from_string(to_wallet)
            # API-FIX: TokenAccountOpts instead of dict
            to_token_resp = await self.client.get_token_accounts_by_owner(
                to_pubkey,
                TokenAccountOpts(mint=self.usdc_mint),
                encoding="jsonParsed"
            )

            if not to_token_resp.value or len(to_token_resp.value) == 0:
                raise ValueError(f"Destination token account not found for wallet {to_wallet}")

            to_token_account = Pubkey.from_string(str(to_token_resp.value[0].pubkey))

            # 4. Convert amount to lamports
            amount_lamports = usdc_to_lamports(amount)
            logger.info(f"Sending {amount} USDC ({amount_lamports} lamports)")

            # 5. Create transfer instruction
            # CRIT-C FIX: Build SPL TransferChecked instruction manually — no spl-token dep
            transfer_ix = _build_transfer_checked_instruction(
                source=from_token_account,
                mint=self.usdc_mint,
                dest=to_token_account,
                owner=keypair.pubkey(),
                amount=amount_lamports,
                decimals=constants.USDC_DECIMALS,
            )

            # 6. Get recent blockhash
            recent_blockhash_resp = await self.client.get_latest_blockhash()
            if not recent_blockhash_resp.value:
                raise ValueError("Failed to get recent blockhash")

            recent_blockhash = recent_blockhash_resp.value.blockhash

            # 7. Build transaction
            tx = SoldersTransaction.new_with_payer(
                [transfer_ix],
                keypair.pubkey()
            )

            # 8. Sign transaction
            # CRIT-A FIX: In solders 0.19, Transaction.sign() requires recent_blockhash
            # as the SECOND argument. The old code set tx.recent_blockhash as an attribute
            # then called tx.sign([keypair]) without blockhash — TypeError at runtime.
            tx.sign([keypair], recent_blockhash)

            # 9. Send transaction
            logger.info("Sending transaction to Solana network...")
            send_resp = await self.client.send_transaction(tx)

            if not send_resp.value:
                raise ValueError("Failed to send transaction")

            signature = str(send_resp.value)
            logger.info(f"Transaction sent: {signature}")

            # 10. Wait for confirmation
            # WARN-4 FIX: In solana-py 0.32, confirm_transaction() returns
            # RpcResponse[SignatureStatuses] where .value is list[Optional[TransactionStatus]].
            # `if confirm_resp.value:` is ALWAYS True (non-empty list) regardless of tx result.
            # Correct check: value[0] is not None (tx found) AND value[0].err is None (no error).
            logger.info("Waiting for confirmation...")
            confirm_resp = await self.client.confirm_transaction(
                Signature.from_string(signature),
                commitment=Confirmed
            )

            confirmed = (
                confirm_resp.value is not None
                and len(confirm_resp.value) > 0
                and confirm_resp.value[0] is not None
                and confirm_resp.value[0].err is None
            )

            if confirmed:
                logger.info(f"✅ USDC sent successfully: {amount} USDC to {to_wallet}")
                logger.info(f"Transaction signature: {signature}")
                return signature
            else:
                err_detail = (
                    confirm_resp.value[0].err
                    if (confirm_resp.value and confirm_resp.value[0])
                    else "unknown error or timeout"
                )
                logger.error(f"❌ Transaction not confirmed: {signature}, error: {err_detail}")
                return None

        except ValueError as e:
            logger.error(f"❌ Validation error sending USDC: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error sending USDC: {e}", exc_info=True)
            return None

    async def is_transaction_confirmed(self, signature: str) -> bool:
        """Check if transaction is confirmed"""
        try:
            tx_info = await self.verify_transaction(signature)
            return tx_info is not None and tx_info.get("confirmed", False)
        except Exception as e:
            logger.error(f"Error checking confirmation: {e}")
            return False

    async def verify_usdc_transaction(
        self,
        tx_hash: str,
        expected_recipient: str,
        expected_amount: Decimal,
        tolerance: Decimal = None  # Z-2 FIX: defaults to constants.AMOUNT_TOLERANCE inside function
    ) -> dict:
        """
        ✅ MODERNIZED: Verify USDC transaction with multi-transfer attack prevention

        BUG-3 FIX: docstring moved to first position in function body so Python
        registers it as __doc__.

        Checks:
        1. Transaction exists on blockchain
        2. Transaction is confirmed
        3. ONLY ONE USDC transfer in transaction (prevents multi-transfer attacks)
        4. Recipient matches expected wallet
        5. Token is USDC
        6. Amount matches expected (within tolerance)

        Returns:
            dict: {
                "valid": bool,
                "amount": Decimal or None,
                "sender": str or None,
                "recipient": str or None,
                "error": str or None
            }
        """
        from config.settings import constants as _c  # Z-2
        if tolerance is None:
            tolerance = _c.AMOUNT_TOLERANCE  # Z-2 FIX: single source of truth
        try:
            await self.connect()

            # Get transaction
            sig = Signature.from_string(tx_hash)
            response = await self.client.get_transaction(
                sig,
                encoding="jsonParsed",
                commitment=Confirmed,
                max_supported_transaction_version=0
            )

            if not response.value:
                return {
                    "valid": False,
                    "amount": None,
                    "sender": None,
                    "recipient": None,
                    "error": "Transaction not found on blockchain"
                }

            tx = response.value

            # Check if transaction has errors
            if tx.transaction.meta and tx.transaction.meta.err:
                return {
                    "valid": False,
                    "amount": None,
                    "sender": None,
                    "recipient": None,
                    "error": f"Transaction failed: {tx.transaction.meta.err}"
                }

            # Parse transaction instructions
            instructions = tx.transaction.transaction.message.instructions

            # ✅ MODERNIZED: Track ALL USDC transfers to prevent multi-transfer attacks
            usdc_transfers = []

            for instruction in instructions:
                if hasattr(instruction, 'parsed'):
                    parsed = instruction.parsed
                    if isinstance(parsed, dict):
                        info = parsed.get('info', {})

                        # Check if it's a transfer or transferChecked
                        if parsed.get('type') in ['transfer', 'transferChecked']:
                            # ✅ Verify it's USDC by checking mint
                            mint = info.get('mint')
                            if mint and mint != str(settings.USDC_MINT):
                                # Not USDC, skip this instruction
                                continue

                            # Get destination
                            destination = info.get('destination')

                            # Get amount
                            if 'tokenAmount' in info:
                                token_amount = info['tokenAmount']
                                amount = Decimal(token_amount.get('uiAmountString', '0'))
                            elif 'amount' in info:
                                raw_amount = int(info['amount'])
                                amount = lamports_to_usdc(raw_amount)
                            else:
                                continue

                            # Record this transfer
                            # CRIT-1: authority = wallet owner (Ed25519 pubkey), source = SPL token account.
                            # CRIT-1 check compares sender to user.wallet_address — must be authority.
                            sender = info.get("authority") or info.get("source")
                            usdc_transfers.append({
                                'destination': destination,
                                'amount': amount,
                                'sender': sender
                            })

                            logger.debug(
                                f"Found USDC transfer: {amount} USDC to {destination}"
                            )

            # ✅ SECURITY: Validate we found exactly ONE USDC transfer
            if len(usdc_transfers) == 0:
                logger.warning(f"No USDC transfers found in transaction {tx_hash}")
                return {
                    "valid": False,
                    "amount": None,
                    "sender": None,
                    "recipient": None,
                    "error": "No USDC transfer found in transaction"
                }

            if len(usdc_transfers) > 1:
                logger.error(
                    f"🚨 SECURITY ALERT: Multiple USDC transfers in single transaction {tx_hash}\n"
                    f"Transfers: {len(usdc_transfers)}"
                )
                for i, transfer in enumerate(usdc_transfers):
                    logger.error(
                        f"  Transfer {i+1}: {transfer['amount']} USDC to {transfer['destination']}"
                    )

                return {
                    "valid": False,
                    "amount": None,
                    "sender": None,
                    "recipient": None,
                    "error": f"Multiple USDC transfers found ({len(usdc_transfers)}) - potential attack detected"
                }

            # Get the single transfer
            transfer = usdc_transfers[0]
            actual_amount = transfer['amount']
            actual_recipient = transfer['destination']
            actual_sender = transfer['sender']

            # ✅ Validate recipient matches
            if actual_recipient != expected_recipient:
                logger.warning(
                    f"Recipient mismatch in transaction {tx_hash}: "
                    f"expected {expected_recipient}, got {actual_recipient}"
                )
                return {
                    "valid": False,
                    "amount": actual_amount,
                    "sender": actual_sender,
                    "recipient": actual_recipient,
                    "error": f"Recipient mismatch: got {actual_recipient}, expected {expected_recipient}"
                }

            # ✅ Validate amount matches (within tolerance)
            amount_diff = abs(actual_amount - expected_amount)
            if amount_diff > tolerance:
                logger.warning(
                    f"Amount mismatch in transaction {tx_hash}: "
                    f"expected {expected_amount}, got {actual_amount}, diff {amount_diff}"
                )
                return {
                    "valid": False,
                    "amount": actual_amount,
                    "sender": actual_sender,
                    "recipient": actual_recipient,
                    "error": f"Amount mismatch: got {actual_amount} USDC, expected {expected_amount} USDC"
                }

            # ✅ All checks passed!
            logger.info(
                f"✅ Transaction verified: {tx_hash}\n"
                f"   Amount: {actual_amount} USDC\n"
                f"   From: {actual_sender}\n"
                f"   To: {actual_recipient}"
            )

            return {
                "valid": True,
                "amount": actual_amount,
                "sender": actual_sender,
                "recipient": actual_recipient,
                "error": None
            }

        except Exception as e:
            logger.error(f"Error verifying USDC transaction: {e}")
            return {
                "valid": False,
                "amount": None,
                "sender": None,
                "recipient": None,
                "error": f"Verification error: {str(e)}"
            }


# Global instance
solana_client = SolanaClient()
