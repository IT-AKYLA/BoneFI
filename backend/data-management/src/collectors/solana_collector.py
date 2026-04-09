import asyncio
import aiohttp
import time
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from random import choice
from concurrent.futures import ThreadPoolExecutor

RPC_ENDPOINTS = os.getenv("RPC_ENDPOINTS", "https://solana.publicnode.com,https://api.mainnet-beta.solana.com").split(",")
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "200"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2000"))
MAX_SIGNATURES = int(os.getenv("MAX_SIGNATURES", "100000"))
USE_WARP = os.getenv("USE_WARP", "false").lower() == "true"
WARP_PROXY_URL = os.getenv("WARP_PROXY_URL", "http://localhost:9091")
MIN_SUCCESS_RATE = float(os.getenv("MIN_SUCCESS_RATE", "70.0"))
COLLECT_MODE = os.getenv("COLLECT_MODE", "latest")
EARLY_SIGNATURES_LIMIT = int(os.getenv("EARLY_SIGNATURES_LIMIT", "100000"))


class SolanaCollector:
    def __init__(self, collect_mode: str = None, early_limit: int = None):
        self.rpc_endpoints = RPC_ENDPOINTS
        self.current_rpc_index = 0
        self.max_concurrent = MAX_CONCURRENT
        self.batch_size = BATCH_SIZE
        self.max_signatures = MAX_SIGNATURES
        self.min_success_rate = MIN_SUCCESS_RATE
        self.collect_mode = collect_mode or COLLECT_MODE
        self.early_limit = early_limit or EARLY_SIGNATURES_LIMIT
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.failed_endpoints = {}
        self.executor = ThreadPoolExecutor(max_workers=4)

    def _get_next_rpc(self) -> str:
        available = [ep for ep in self.rpc_endpoints if self.failed_endpoints.get(ep, 0) < 3]
        if not available:
            self.failed_endpoints.clear()
            available = self.rpc_endpoints
        return choice(available)

    def _mark_failed(self, endpoint: str):
        self.failed_endpoints[endpoint] = self.failed_endpoints.get(endpoint, 0) + 1

    async def __aenter__(self):
        connector = None
        if USE_WARP and WARP_PROXY_URL:
            connector = aiohttp.TCPConnector(limit=0, limit_per_host=0, ttl_dns_cache=300)
            self.session = aiohttp.ClientSession(
                connector=connector,
                trust_env=True
            )
        else:
            connector = aiohttp.TCPConnector(limit=0, limit_per_host=0, ttl_dns_cache=300)
            self.session = aiohttp.ClientSession(connector=connector)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        self.executor.shutdown(wait=False)

    async def _rpc_call(self, method: str, params: List, retry: int = 2) -> Optional[Dict]:
        for attempt in range(retry + 1):
            rpc_url = self._get_next_rpc()
            
            async with self.semaphore:
                try:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params
                    }
                    
                    async with self.session.post(
                        rpc_url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        result = await resp.json()
                        
                        if "error" in result:
                            self._mark_failed(rpc_url)
                            if attempt < retry:
                                await asyncio.sleep(0.5 * (attempt + 1))
                                continue
                            return None
                        return result
                        
                except Exception:
                    self._mark_failed(rpc_url)
                    if attempt < retry:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    return None
        
        return None

    async def get_token_supply(self, mint: str) -> Dict:
        result = await self._rpc_call("getTokenSupply", [mint])
        if result and "result" in result:
            supply_data = result["result"]["value"]
            return {
                "decimals": supply_data["decimals"],
                "supply": int(supply_data["amount"]),
                "supply_formatted": int(supply_data["amount"]) / (10 ** supply_data["decimals"])
            }
        return {}

    async def get_all_signatures(self, token_mint: str) -> List[str]:
        if self.collect_mode == "earliest":
            print(f"   Fetching earliest {self.early_limit} signatures...")
            return await self._get_earliest_signatures(token_mint)
        else:
            print(f"   Fetching latest signatures (max: {self.max_signatures})...")
            return await self._get_latest_signatures(token_mint)
    
    async def _get_latest_signatures(self, token_mint: str) -> List[str]:
        signatures = []
        before = None
        page = 0
        
        while True:
            page += 1
            params = [token_mint, {"limit": 1000}]
            if before:
                params[1]["before"] = before
            
            result = await self._rpc_call("getSignaturesForAddress", params)
            
            if not result or "result" not in result:
                break
            
            batch = result["result"]
            if not batch:
                break
            
            for sig in batch:
                signatures.append(sig["signature"])
            
            before = batch[-1]["signature"]
            print(f"   Page {page}: +{len(batch)} signatures (total: {len(signatures)})")
            
            if len(signatures) >= self.max_signatures:
                signatures = signatures[:self.max_signatures]
                break
            
            if len(batch) < 1000:
                break
            
            await asyncio.sleep(0.05)
        
        return signatures
    
    async def _get_earliest_signatures(self, token_mint: str) -> List[str]:
        signatures = []
        until = None
        page = 0
        
        while True:
            page += 1
            params = [token_mint, {"limit": 1000}]
            if until:
                params[1]["until"] = until
            
            result = await self._rpc_call("getSignaturesForAddress", params)
            
            if not result or "result" not in result:
                break
            
            batch = result["result"]
            if not batch:
                break
            
            for sig in batch:
                signatures.append(sig["signature"])
            
            until = batch[-1]["signature"]
            print(f"   Page {page}: +{len(batch)} signatures (total: {len(signatures)})")
            
            if len(signatures) >= self.early_limit:
                signatures = signatures[:self.early_limit]
                break
            
            if len(batch) < 1000:
                break
            
            await asyncio.sleep(0.05)
        
        return signatures

    async def fetch_transaction(self, signature: str) -> Optional[Dict]:
        result = await self._rpc_call(
            "getTransaction",
            [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0}]
        )
        if result and "result" in result and result["result"]:
            return result["result"]
        return None

    async def fetch_transactions_batch(self, signatures: List[str]) -> List[Dict]:
        tasks = [self.fetch_transaction(sig) for sig in signatures]
        responses = await asyncio.gather(*tasks)
        return [tx for tx in responses if tx is not None]

    async def fetch_transactions_parallel(self, signatures: List[str]) -> List[Dict]:
        total = len(signatures)
        all_transactions = []
        
        # Уменьшаем batch_size для больших токенов
        actual_batch_size = min(self.batch_size, 500)  # Максимум 500 за раз
        
        for i in range(0, total, actual_batch_size):
            batch = signatures[i:i + actual_batch_size]
            batch_start = time.time()
            
            try:
                # Добавляем таймаут на batch
                batch_txs = await asyncio.wait_for(
                    self.fetch_transactions_batch(batch),
                    timeout=60.0
                )
                all_transactions.extend(batch_txs)
                
                elapsed = time.time() - batch_start
                rate = len(batch_txs) / elapsed if elapsed > 0 else 0
                print(f"      Batch {i//actual_batch_size + 1}: {len(batch_txs)}/{len(batch)} txs ({rate:.1f} tx/sec)")
                
            except asyncio.TimeoutError:
                print(f"      Batch {i//actual_batch_size + 1}: TIMEOUT after 60 seconds")
                continue
            
            # Задержка между батчами
            await asyncio.sleep(0.5)
        
        return all_transactions

    async def collect(self, token_mint: str, force: bool = False) -> Tuple[bool, Dict]:
        start_time = time.time()
        
        print(f"\n{'='*60}")
        print(f"Collecting token: {token_mint}")
        print(f"Mode: {self.collect_mode}")
        if self.collect_mode == "earliest":
            print(f"Early limit: {self.early_limit} signatures")
        else:
            print(f"Max signatures: {self.max_signatures}")
        print(f"{'='*60}\n")
        
        token_info = await self.get_token_supply(token_mint)
        
        signatures = await self.get_all_signatures(token_mint)
        if not signatures:
            return False, {}
        
        transactions = await self.fetch_transactions_parallel(signatures)
        
        elapsed = time.time() - start_time
        success_rate = (len(transactions) / len(signatures) * 100) if signatures else 0
        
        is_valid = success_rate >= self.min_success_rate
        
        data = {
            "token_mint": token_mint,
            "token_info": token_info,
            "collected_at": datetime.now().isoformat(),
            "total_signatures": len(signatures),
            "total_transactions": len(transactions),
            "signatures": signatures if is_valid else [],
            "transactions": transactions if is_valid else [],
            "collection_time_seconds": elapsed,
            "success_rate": success_rate,
            "is_valid": is_valid,
            "force_saved": force,
            "collect_mode": self.collect_mode,
            "collect_limit": self.early_limit if self.collect_mode == "earliest" else self.max_signatures
        }
        
        if not is_valid and not force:
            print(f"\n   ⚠️ Invalid data: success rate {success_rate:.1f}% < {self.min_success_rate}%")
            print(f"   Skipping save. Use force=True to override")
            return False, data
        
        print(f"\n{'='*60}")
        print(f"Collection complete!")
        print(f"  Signatures: {len(signatures)}")
        print(f"  Transactions: {len(transactions)}")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  Time: {elapsed:.2f}s")
        print(f"{'='*60}\n")
        
        return True, data