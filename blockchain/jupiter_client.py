"""
blockchain/jupiter_client.py — USDC→SOL swap via Jupiter Aggregator v6.

Jupiter is the leading DEX aggregator on Solana. It finds the best route
across all liquidity pools (Orca, Raydium, Meteora, etc.) and returns a
ready-to-sign transaction.

Flow:
  1. GET /quote  — ask Jupiter for the best USDC→SOL rate for our amount
  2. POST /swap  — Jupiter returns a base64-encoded transaction
  3. Sign the transaction with HOT_WALLET_PRIVATE_KEY
  4. Submit to Solana RPC and wait for confirmation

No API key required for the public Jupiter endpoint.
Docs: https://station.jup.ag/docs/apis/swap-api

Fee note:
  The swap itself costs ~0.000005 SOL in Solana network fees.
  For the very first swap (when SOL balance is zero) this creates a
  chicken-and-egg problem. Solution: Jupiter's swap transaction includes
  an "unwrap" instruction that converts wrapped SOL to native SOL,
  so even starting from zero SOL the first swap works as long as the
  Solana runtime can front the fee (it can for small amounts via fee payer).
  In practice: keep at least 0.001 SOL as a seed on the hot wallet when
  setting up the project for the first time.
"""

import logging
import base64
from decimal import Decimal
from typing import Optional

from config.settings import settings, constants

logger = logging.getLogger(__name__)

# USDC has 6 decimal places on Solana
USDC_DECIMALS = 6
# SOL (wrapped) has 9 decimal places
SOL_DECIMALS  = 9


class JupiterClient:
    """
    Minimal Jupiter v6 Swap API client.

    Only implements quote + swap for USDC→SOL (the gas funding use case).
    Uses aiohttp for async HTTP — same event loop as the rest of the app.
    """

    def __init__(self):
        self.base_url = settings.JUPITER_API_URL.rstrip("/")
        self.usdc_mint = settings.USDC_MINT
        self.sol_mint  = settings.SOL_MINT
        self.max_slippage_bps = settings.JUPITER_MAX_SLIPPAGE_BPS

    async def get_quote(self, usdc_amount: Decimal, http_session=None) -> Optional[dict]:
        """
        GET /quote — fetch best USDC→SOL swap route.

        Args:
            usdc_amount: Amount of USDC to swap (e.g. Decimal("0.99"))

        Returns:
            Jupiter quote dict on success, None on failure.
            Key fields in the quote:
              inAmount:      str  — USDC lamports in
              outAmount:     str  — SOL lamports out (estimated)
              priceImpactPct: str — price impact as percentage string
              routePlan:     list — swap route details
        """
        import aiohttp

        # Jupiter expects amounts in token lamports (smallest unit)
        usdc_lamports = int(usdc_amount * Decimal(10 ** USDC_DECIMALS))

        params = {
            "inputMint":   self.usdc_mint,
            "outputMint":  self.sol_mint,
            "amount":      str(usdc_lamports),
            "slippageBps": str(self.max_slippage_bps),
            # swapMode=ExactIn: we specify exact USDC in, get best SOL out
            "swapMode":    "ExactIn",
            # onlyDirectRoutes=false: allow multi-hop for better rates
            "onlyDirectRoutes": "false",
        }

        url = f"{self.base_url}/quote"

        async def _fetch_quote(http):
            async with http.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Jupiter /quote returned {resp.status}: {body[:200]}")
                    return None
                return await resp.json()

        try:
            if http_session is not None:
                quote = await _fetch_quote(http_session)
            else:
                async with aiohttp.ClientSession() as http:
                    quote = await _fetch_quote(http)
            if quote is None:
                return None

            # Validate price impact — reject if too high.
            # UNIT FIX: Jupiter returns priceImpactPct as a PERCENTAGE string,
            # e.g. "0.05" means 0.05% price impact (NOT the fraction 0.0005).
            # We express the threshold in the same unit: bps / 100 → percent.
            # e.g. 50 bps → 50/100 = 0.50%
            # Dividing by 10000 would give 0.005, making 0.05 > 0.005 = True
            # and rejecting virtually every quote. Correct divisor is 100.
            price_impact = Decimal(str(quote.get("priceImpactPct", "0")))
            max_impact = Decimal(self.max_slippage_bps) / Decimal("100")  # bps → %

            if price_impact > max_impact:
                logger.warning(
                    f"Jupiter quote rejected: price impact {price_impact}% "
                    f"exceeds max {max_impact}% ({self.max_slippage_bps} bps)"
                )
                return None

            sol_out = Decimal(quote["outAmount"]) / Decimal(10 ** SOL_DECIMALS)
            logger.info(
                f"Jupiter quote: {usdc_amount} USDC → {sol_out:.6f} SOL "
                f"(impact: {price_impact}%)"
            )
            return quote

        except Exception as e:
            logger.error(f"Jupiter /quote error: {e}", exc_info=True)
            return None

    async def build_swap_transaction(self, quote: dict, user_public_key: str, http_session=None) -> Optional[str]:
        """
        POST /swap — build the swap transaction.

        Jupiter returns a base64-encoded versioned transaction ready to sign.

        Args:
            quote:           Quote dict from get_quote()
            user_public_key: Base58 public key of the signing wallet (hot wallet)

        Returns:
            Base64-encoded transaction string, or None on failure.
        """
        import aiohttp

        payload = {
            "quoteResponse":            quote,
            "userPublicKey":            user_public_key,
            # wrapAndUnwrapSol=true: Jupiter handles wrapping USDC→wSOL automatically
            # and unwraps the output wSOL to native SOL
            "wrapAndUnwrapSol":         True,
            # dynamicComputeUnitLimit: let Jupiter estimate compute units
            "dynamicComputeUnitLimit":  True,
            # prioritizationFeeLamports: auto-set priority fee for faster confirmation
            "prioritizationFeeLamports": "auto",
        }

        url = f"{self.base_url}/swap"

        async def _fetch_swap(http):
            async with http.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Jupiter /swap returned {resp.status}: {body[:200]}")
                    return None
                return await resp.json()

        try:
            if http_session is not None:
                data = await _fetch_swap(http_session)
            else:
                async with aiohttp.ClientSession() as http:
                    data = await _fetch_swap(http)
            if data is None:
                return None

            swap_tx_b64 = data.get("swapTransaction")
            if not swap_tx_b64:
                logger.error(f"Jupiter /swap response missing swapTransaction: {data}")
                return None

            logger.debug("Jupiter swap transaction built successfully")
            return swap_tx_b64

        except Exception as e:
            logger.error(f"Jupiter /swap error: {e}", exc_info=True)
            return None

    async def swap_usdc_to_sol(self, usdc_amount: Decimal) -> Optional[str]:
        """
        Full USDC→SOL swap: quote → build tx → sign → submit → confirm.

        Args:
            usdc_amount: USDC amount to swap (e.g. Decimal("0.99"))

        Returns:
            Solana transaction signature (str) on success, None on failure.
        """
        from solders.keypair import Keypair
        from solders.transaction import VersionedTransaction
        from solana.rpc.commitment import Confirmed
        from solders.signature import Signature
        from blockchain.solana_client import solana_client

        if usdc_amount <= Decimal("0"):
            logger.error(f"swap_usdc_to_sol: invalid amount {usdc_amount}")
            return None

        logger.info(f"🔄 Swapping {usdc_amount} USDC → SOL via Jupiter...")

        try:
            # ── 1. Get private key ────────────────────────────────────────────
            private_key = None
            try:
                from security.key_management import get_key_manager
                km = get_key_manager(
                    aws_region=getattr(settings, "AWS_REGION", "us-east-1"),
                    kms_key_id=getattr(settings, "KMS_KEY_ID", None),
                )
                private_key = await km.get_private_key()
            except Exception:
                private_key = settings.HOT_WALLET_PRIVATE_KEY

            if not private_key:
                logger.error("No HOT_WALLET_PRIVATE_KEY available for Jupiter swap")
                return None

            keypair = Keypair.from_base58_string(private_key)
            wallet_pubkey_str = str(keypair.pubkey())

            # ── 2. Get quote + build tx — share ONE aiohttp.ClientSession ────
            # Each call previously opened its own TCP connection to Jupiter.
            # Sharing one session reuses the connection for both HTTP calls,
            # cutting latency and avoiding ResourceWarning from unclosed connectors.
            import aiohttp as _aiohttp
            async with _aiohttp.ClientSession() as _http:
                quote = await self.get_quote(usdc_amount, http_session=_http)
                if not quote:
                    logger.error(f"Could not get Jupiter quote for {usdc_amount} USDC")
                    return None

                # ── 3. Build transaction ──────────────────────────────────────
                swap_tx_b64 = await self.build_swap_transaction(
                    quote, wallet_pubkey_str, http_session=_http
                )
            # _http session closes here
            if not swap_tx_b64:
                logger.error("Could not build Jupiter swap transaction")
                return None

            # ── 4. Deserialize, sign, serialize ──────────────────────────────
            # Jupiter returns a VersionedTransaction (v0 with address lookup tables).
            # CRITICAL: In solders, VersionedTransaction is IMMUTABLE.
            # versioned_tx.sign([keypair]) does NOT mutate in place — it returns
            # a new signed transaction. The correct API is to construct a new
            # VersionedTransaction with the original message and our keypair as signer.
            # Wrong:  versioned_tx.sign([keypair]); bytes(versioned_tx)  ← unsigned!
            # Correct: signed_tx = VersionedTransaction(versioned_tx.message, [keypair])
            raw_tx_bytes = base64.b64decode(swap_tx_b64)
            unsigned_tx  = VersionedTransaction.from_bytes(raw_tx_bytes)
            signed_tx    = VersionedTransaction(unsigned_tx.message, [keypair])
            signed_bytes = bytes(signed_tx)

            # ── 5. Submit ─────────────────────────────────────────────────────
            await solana_client.connect()
            send_resp = await solana_client.client.send_raw_transaction(signed_bytes)

            if not send_resp.value:
                logger.error("Jupiter swap: send_raw_transaction returned no signature")
                return None

            signature = str(send_resp.value)
            logger.info(f"Jupiter swap submitted: {signature}")

            # ── 6. Confirm ────────────────────────────────────────────────────
            confirm_resp = await solana_client.client.confirm_transaction(
                Signature.from_string(signature),
                commitment=Confirmed,
            )

            confirmed = (
                confirm_resp.value is not None
                and len(confirm_resp.value) > 0
                and confirm_resp.value[0] is not None
                and confirm_resp.value[0].err is None
            )

            if confirmed:
                sol_received = Decimal(quote["outAmount"]) / Decimal(10 ** SOL_DECIMALS)
                logger.info(
                    f"✅ Jupiter swap confirmed: {usdc_amount} USDC → {sol_received:.6f} SOL "
                    f"(tx: {signature})"
                )
                return signature
            else:
                err = (confirm_resp.value[0].err
                       if confirm_resp.value and confirm_resp.value[0] else "timeout")
                logger.error(f"❌ Jupiter swap not confirmed: {signature}, err={err}")
                return None

        except Exception as e:
            logger.error(f"❌ Jupiter swap_usdc_to_sol error: {e}", exc_info=True)
            return None


# Global singleton — reused across requests/tasks
jupiter_client = JupiterClient()
