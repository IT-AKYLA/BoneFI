from fastapi import APIRouter, HTTPException
from typing import List, Dict

from ...core.database import RedisCache, get_redis_client

router = APIRouter()


@router.get("/tokens")
async def list_tokens(limit: int = 20) -> List[Dict]:
    client = await get_redis_client()
    cache = RedisCache(client)
    return await cache.get_all_tokens(limit)


@router.get("/token/{mint}")
async def get_token(mint: str) -> Dict:
    client = await get_redis_client()
    cache = RedisCache(client)
    
    data = await cache.get_token(mint)
    
    if not data:
        raise HTTPException(status_code=404, detail="Token not found")
    
    return {
        "token_mint": mint,
        "total_transactions": data.get("total_transactions", 0),
        "total_signatures": data.get("total_signatures", 0),
        "success_rate": data.get("success_rate", 0),
        "collection_time_seconds": data.get("collection_time_seconds", 0),
        "collected_at": data.get("collected_at"),
        "token_info": data.get("token_info", {})
    }