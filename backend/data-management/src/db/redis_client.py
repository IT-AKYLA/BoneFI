import redis.asyncio as redis
from redis.asyncio import ConnectionPool
from typing import Optional, Any, List, Dict
import json
import gzip
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", "20"))
REDIS_SOCKET_CONNECT_TIMEOUT = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "20"))
COMPRESSION_LEVEL = int(os.getenv("COMPRESSION_LEVEL", "9"))

_pool: Optional[ConnectionPool] = None
_client: Optional[redis.Redis] = None
_executor = ThreadPoolExecutor(max_workers=4)


async def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            REDIS_URL,
            max_connections=REDIS_MAX_CONNECTIONS,
            socket_timeout=REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
            decode_responses=False
        )
    return _pool


async def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        pool = await get_redis_pool()
        _client = redis.Redis(connection_pool=pool)
    return _client


async def close_redis_connection():
    global _client, _pool
    if _client:
        await _client.close()
        _client = None
    if _pool:
        await _pool.disconnect()
        _pool = None
    _executor.shutdown(wait=False)


def _compress_sync(data: Any) -> bytes:
    json_str = json.dumps(data, default=str, separators=(',', ':'))
    return gzip.compress(json_str.encode('utf-8'), compresslevel=COMPRESSION_LEVEL)


def _decompress_sync(data: bytes) -> Any:
    decompressed = gzip.decompress(data)
    return json.loads(decompressed.decode('utf-8'))


class RedisCache:
    def __init__(self, client: Optional[redis.Redis] = None):
        self._client = client
        self._local_cache: Dict[str, tuple] = {}
        self._cache_ttl = 60

    async def _get_client(self) -> redis.Redis:
        if self._client:
            return self._client
        return await get_redis_client()

    async def _compress(self, data: Any) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _compress_sync, data)

    async def _decompress(self, data: bytes) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _decompress_sync, data)

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        client = await self._get_client()
        compressed = await self._compress(value)
        
        self._local_cache[key] = (value, asyncio.get_event_loop().time())
        
        if ttl:
            return await client.setex(key, ttl, compressed)
        return await client.set(key, compressed)

    async def get_json(self, key: str, use_cache: bool = True) -> Optional[Any]:
        if use_cache and key in self._local_cache:
            data, timestamp = self._local_cache[key]
            if asyncio.get_event_loop().time() - timestamp < self._cache_ttl:
                return data
        
        client = await self._get_client()
        data = await client.get(key)
        if data:
            result = await self._decompress(data)
            self._local_cache[key] = (result, asyncio.get_event_loop().time())
            return result
        return None

    async def get_json_batch(self, keys: List[str], use_cache: bool = True) -> Dict[str, Any]:
        results = {}
        missing_keys = []
        
        for key in keys:
            if use_cache and key in self._local_cache:
                data, timestamp = self._local_cache[key]
                if asyncio.get_event_loop().time() - timestamp < self._cache_ttl:
                    results[key] = data
                    continue
            missing_keys.append(key)
        
        if missing_keys:
            client = await self._get_client()
            pipeline = client.pipeline()
            for key in missing_keys:
                pipeline.get(key)
            responses = await pipeline.execute()
            
            for key, data in zip(missing_keys, responses):
                if data:
                    result = await self._decompress(data)
                    results[key] = result
                    self._local_cache[key] = (result, asyncio.get_event_loop().time())
        
        return results

    async def set_json_batch(self, items: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        client = await self._get_client()
        pipeline = client.pipeline()
        
        current_time = asyncio.get_event_loop().time()
        
        for key, value in items.items():
            compressed = await self._compress(value)
            if ttl:
                pipeline.setex(key, ttl, compressed)
            else:
                pipeline.set(key, compressed)
            self._local_cache[key] = (value, current_time)
        
        await pipeline.execute()
        return True

    async def delete(self, key: str) -> int:
        client = await self._get_client()
        self._local_cache.pop(key, None)
        return await client.delete(key)

    async def exists(self, key: str) -> bool:
        client = await self._get_client()
        return await client.exists(key) > 0

    async def hset_json(self, name: str, key: str, value: Any) -> int:
        client = await self._get_client()
        compressed = await self._compress(value)
        return await client.hset(name, key, compressed)

    async def hget_json(self, name: str, key: str) -> Optional[Any]:
        client = await self._get_client()
        data = await client.hget(name, key)
        if data:
            return await self._decompress(data)
        return None

    async def hget_all_json(self, name: str) -> Dict[str, Any]:
        client = await self._get_client()
        data = await client.hgetall(name)
        result = {}
        for k, v in data.items():
            try:
                key_str = k.decode('utf-8') if isinstance(k, bytes) else k
                result[key_str] = await self._decompress(v)
            except Exception:
                key_str = k.decode('utf-8') if isinstance(k, bytes) else k
                result[key_str] = v
        return result

    async def zadd(self, key: str, score: float, member: str) -> int:
        client = await self._get_client()
        return await client.zadd(key, {member: score})

    async def zrevrange_with_scores(self, key: str, start: int, stop: int) -> List[tuple]:
        client = await self._get_client()
        return await client.zrevrange(key, start, stop, withscores=True)

    async def lpush_json(self, key: str, value: Any, max_length: Optional[int] = None) -> int:
        client = await self._get_client()
        compressed = await self._compress(value)
        result = await client.lpush(key, compressed)
        if max_length:
            await client.ltrim(key, 0, max_length - 1)
        return result

    async def lrange_json(self, key: str, start: int, stop: int) -> List[Any]:
        client = await self._get_client()
        data = await client.lrange(key, start, stop)
        result = []
        for item in data:
            try:
                result.append(await self._decompress(item))
            except Exception:
                result.append(item)
        return result

    async def incr(self, key: str) -> int:
        client = await self._get_client()
        return await client.incr(key)

    async def expire(self, key: str, ttl: int) -> bool:
        client = await self._get_client()
        return await client.expire(key, ttl)

    def clear_local_cache(self):
        self._local_cache.clear()