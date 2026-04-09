# data-management/src/db/status.py
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(os.path.join(Path(__file__).parent.parent.parent, "data-management", ".env"))

from src.db.redis_client import get_redis_client, RedisCache
from src.db.cache_keys import CacheKeys


async def show_status():
    client = await get_redis_client()
    cache = RedisCache(client)
    
    print("\n" + "=" * 50)
    print("REDIS STATUS")
    print("=" * 50)
    
    info = await client.info("memory")
    used_mb = int(info.get("used_memory", 0)) / 1024 / 1024
    print(f"Memory used: {used_mb:.2f} MB")
    
    keys = await client.keys("*")
    print(f"Total keys: {len(keys)}")
    
    token_keys = await client.keys(f"{CacheKeys.TOKEN_PREFIX}*")
    print(f"Token keys: {len(token_keys)}")
    
    if token_keys:
        print("\n📋 Tokens in cache:")
        for key in token_keys[:10]:
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            mint = key.replace(CacheKeys.TOKEN_PREFIX, "")
            
            raw_data = await client.get(key)
            raw_size_mb = len(raw_data) / 1024 / 1024 if raw_data else 0
            
            data = await cache.get_json(key)
            if data:
                orig_size_mb = len(json.dumps(data)) / 1024 / 1024
                print(f"   {mint[:30]}...")
                print(f"      Raw in Redis: {raw_size_mb:.2f} MB")
                print(f"      Original JSON: {orig_size_mb:.2f} MB")
                print(f"      Compression: {orig_size_mb/raw_size_mb:.1f}x")
                print(f"      Transactions: {data.get('total_transactions', 0)}")
    
    await client.aclose()


if __name__ == "__main__":
    import json
    asyncio.run(show_status())