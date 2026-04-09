# data-management/migrate_metadata.py
import asyncio
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.db import get_redis_client, RedisCache, CacheKeys

async def migrate():
    print("Creating metadata for existing tokens...")
    
    client = await get_redis_client()
    cache = RedisCache(client)
    
    keys = await client.keys(f"{CacheKeys.TOKEN_PREFIX}*")
    print(f"Found {len(keys)} tokens")
    
    for key in keys:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        mint = key.replace(CacheKeys.TOKEN_PREFIX, "")
        
        # Проверяем, есть ли уже метаданные
        existing = await client.get(CacheKeys.meta_key(mint))
        if existing:
            print(f"⏭️ Skipping {mint[:16]}... (metadata exists)")
            continue
        
        print(f"📦 Processing {mint[:16]}...")
        
        data = await cache.get_json(key)
        if data:
            metadata = {
                "total_transactions": data.get("total_transactions", 0),
                "total_signatures": data.get("total_signatures", 0),
                "success_rate": data.get("success_rate", 0),
                "collected_at": data.get("collected_at", ""),
                "token_info": data.get("token_info", {}),
                "collection_time_seconds": data.get("collection_time_seconds", 0)
            }
            await cache.set_json(CacheKeys.meta_key(mint), metadata, ttl=86400)
            print(f"  ✅ Created metadata for {mint[:16]}...")
        else:
            print(f"  ❌ Failed to get data for {mint[:16]}...")
    
    print("\n✅ Migration complete!")
    await client.aclose()

if __name__ == "__main__":
    asyncio.run(migrate())