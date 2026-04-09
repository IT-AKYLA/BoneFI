# data-analysis/src/core/database.py
import redis.asyncio as redis
from redis.asyncio import ConnectionPool
import json
import gzip
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Any, List, Dict
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", "10"))
REDIS_SOCKET_CONNECT_TIMEOUT = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "10"))
REDIS_DECODE_RESPONSES = False
REDIS_RETRY_ATTEMPTS = int(os.getenv("REDIS_RETRY_ATTEMPTS", "3"))
REDIS_RETRY_DELAY = float(os.getenv("REDIS_RETRY_DELAY", "0.5"))

_pool: Optional[ConnectionPool] = None
_client: Optional[redis.Redis] = None

_tokens_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": None,
    "limit": None
}
TOKENS_CACHE_TTL = int(os.getenv("TOKENS_CACHE_TTL", "10"))


async def get_redis_client() -> redis.Redis:
    global _client, _pool
    if _client is None:
        _pool = ConnectionPool.from_url(
            REDIS_URL,
            max_connections=REDIS_MAX_CONNECTIONS,
            socket_timeout=REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
            decode_responses=REDIS_DECODE_RESPONSES
        )
        _client = redis.Redis(connection_pool=_pool)
    return _client


async def close_redis_connection():
    global _client, _pool
    if _client:
        await _client.close()
        _client = None
    if _pool:
        await _pool.disconnect()
        _pool = None


class RedisCache:
    def __init__(self, client: Optional[redis.Redis] = None):
        self._client = client

    async def _get_client(self) -> redis.Redis:
        if self._client:
            return self._client
        return await get_redis_client()

    def _decompress(self, data: bytes) -> Any:
        try:
            decompressed = gzip.decompress(data)
            return json.loads(decompressed.decode('utf-8'))
        except Exception as e:
            print(f"Decompression error: {e}")
            return None

    def _compress(self, data: dict) -> bytes:
        """Сжимает данные для сохранения в Redis"""
        json_str = json.dumps(data, default=str)
        return gzip.compress(json_str.encode('utf-8'), compresslevel=9)

    async def get_token(self, mint: str, retry: int = None) -> Optional[dict]:
        client = await self._get_client()
        key = f"token:{mint}"
        max_retries = retry or REDIS_RETRY_ATTEMPTS
        
        for attempt in range(max_retries):
            try:
                data = await client.get(key)
                if data:
                    return self._decompress(data)
                return None
            except (asyncio.TimeoutError, ConnectionError) as e:
                if attempt < max_retries - 1:
                    print(f"Redis timeout for {mint}, retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(REDIS_RETRY_DELAY * (attempt + 1))
                    continue
                print(f"Redis error for {mint}: {e}")
                return None
            except Exception as e:
                print(f"Unexpected error for {mint}: {e}")
                return None
        return None

    async def get_all_tokens(self, limit: int = 20) -> List[Dict]:
        global _tokens_cache
        
        if (_tokens_cache["data"] is not None and 
            _tokens_cache["timestamp"] is not None and
            _tokens_cache["limit"] == limit):
            cache_age = (datetime.now() - _tokens_cache["timestamp"]).seconds
            if cache_age < TOKENS_CACHE_TTL:
                return _tokens_cache["data"]
        
        client = await self._get_client()
        
        try:
            keys = await asyncio.wait_for(client.keys("token:*"), timeout=5.0)
        except asyncio.TimeoutError:
            print("Redis timeout getting keys, returning cached data if available")
            if _tokens_cache["data"] is not None:
                return _tokens_cache["data"][:limit]
            return []
        
        if not keys:
            return []
        
        string_keys = []
        for key in keys[:limit]:
            if isinstance(key, bytes):
                string_keys.append(key.decode('utf-8'))
            else:
                string_keys.append(key)
        
        keys = keys[:min(limit, len(keys))]
        
        pipeline = client.pipeline()
        for key in string_keys:
            pipeline.get(key)
        
        try:
            results = await asyncio.wait_for(pipeline.execute(), timeout=30)
        except asyncio.TimeoutError:
            print("Redis pipeline timeout")
            if _tokens_cache["data"] is not None:
                return _tokens_cache["data"][:limit]
            return []
        
        tokens = []
        for i, data in enumerate(results):
            if data:
                key = keys[i]
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                mint = key.replace("token:", "")
                
                try:
                    decompressed_data = self._decompress(data)
                    if decompressed_data:
                        tokens.append({
                            "token_mint": mint,
                            "total_transactions": decompressed_data.get("total_transactions", 0),
                            "total_signatures": decompressed_data.get("total_signatures", 0),
                            "success_rate": decompressed_data.get("success_rate", 0),
                            "collected_at": decompressed_data.get("collected_at", "")
                        })
                except Exception as e:
                    print(f"Error decompressing data for {mint}: {e}")
                    continue
        
        _tokens_cache["data"] = tokens
        _tokens_cache["timestamp"] = datetime.now()
        _tokens_cache["limit"] = limit
        
        return tokens[:limit]

    async def get_token_batch(self, mints: List[str]) -> Dict[str, Optional[dict]]:
        if not mints:
            return {}
        
        client = await self._get_client()
        pipeline = client.pipeline()
        
        for mint in mints:
            pipeline.get(f"token:{mint}")
        
        try:
            results = await asyncio.wait_for(pipeline.execute(), timeout=10.0)
        except asyncio.TimeoutError:
            print("Redis pipeline timeout in batch")
            return {mint: None for mint in mints}
        
        tokens = {}
        for i, mint in enumerate(mints):
            if results[i]:
                tokens[mint] = self._decompress(results[i])
            else:
                tokens[mint] = None
        
        return tokens

    # ========== НОВЫЕ МЕТОДЫ ДЛЯ ИСТОРИИ ==========

    async def save_analysis_history(self, token_mint: str, analysis_data: dict, ttl: int = 604800) -> bool:
        """Сохраняет результат анализа в историю (TTL по умолчанию 7 дней)"""
        client = await self._get_client()
        key = f"history:{token_mint}"
        
        try:
            # Добавляем timestamp если его нет
            if "analyzed_at" not in analysis_data:
                analysis_data["analyzed_at"] = datetime.now().isoformat()
            
            compressed = self._compress(analysis_data)
            await client.setex(key, ttl, compressed)
            return True
        except Exception as e:
            print(f"Error saving history for {token_mint}: {e}")
            return False

    async def get_analysis_history(self, token_mint: str) -> Optional[dict]:
        """Получает исторический анализ токена"""
        client = await self._get_client()
        key = f"history:{token_mint}"
        
        try:
            data = await client.get(key)
            if data:
                return self._decompress(data)
            return None
        except Exception as e:
            print(f"Error getting history for {token_mint}: {e}")
            return None

    async def add_to_daily_analytics(self, token_mint: str, risk_score: int) -> None:
        """Добавляет токен в ежедневную аналитику"""
        client = await self._get_client()
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"analytics:daily:{today}"
        await client.zadd(key, {token_mint: risk_score})
        await client.expire(key, 86400 * 30)  # 30 дней

    async def get_daily_top_tokens(self, limit: int = 50) -> List[tuple]:
        """Получает топ токенов за сегодня по риску"""
        client = await self._get_client()
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"analytics:daily:{today}"
        return await client.zrevrange(key, 0, limit - 1, withscores=True)

    async def get_historical_analytics(self, days: int = 7) -> dict:
        """Получает аналитику за последние N дней"""
        client = await self._get_client()
        result = {}
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            key = f"analytics:daily:{date}"
            count = await client.zcard(key)
            result[date] = count
        return result

    async def get_all_history_keys(self, limit: int = 100) -> List[str]:
        """Получает все ключи истории"""
        client = await self._get_client()
        keys = await client.keys("history:*")
        if isinstance(keys[0], bytes):
            return [k.decode('utf-8') for k in keys[:limit]]
        return keys[:limit]