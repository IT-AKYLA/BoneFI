# data-analysis/src/api/routes/history.py
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from ...core.database import RedisCache, get_redis_client

router = APIRouter()


@router.get("/history/{mint}")
async def get_token_history(mint: str) -> Dict:
    """Получает исторический анализ токена"""
    client = await get_redis_client()
    cache = RedisCache(client)
    
    history = await cache.get_analysis_history(mint)
    if not history:
        raise HTTPException(status_code=404, detail="No history found for this token")
    
    return history


@router.delete("/history/{mint}")
async def delete_token_history(mint: str) -> Dict:
    """Удаляет историю токена"""
    client = await get_redis_client()
    cache = RedisCache(client)
    
    key = f"history:{mint}"
    deleted = await client.delete(key)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="No history found for this token")
    
    return {"status": "deleted", "token_mint": mint}


@router.get("/analytics/stats")
async def get_analytics_stats() -> Dict:
    """Получает общую статистику по истории анализов"""
    client = await get_redis_client()
    
    # Просто считаем количество history ключей
    keys = await client.keys("history:*")
    total_analyzed = len(keys)
    
    # Считаем по уровням риска (ограничим для производительности)
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0
    
    for key in keys[:200]:  # Ограничиваем для скорости
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        mint = key.replace("history:", "")
        history = await client.get(key)
        if history:
            import json
            import gzip
            try:
                decompressed = gzip.decompress(history)
                data = json.loads(decompressed.decode('utf-8'))
                risk_level = data.get("risk_assessment", {}).get("level", "UNKNOWN")
                if risk_level == "CRITICAL":
                    critical_count += 1
                elif risk_level == "HIGH":
                    high_count += 1
                elif risk_level == "MEDIUM":
                    medium_count += 1
                elif risk_level == "LOW":
                    low_count += 1
            except:
                pass
    
    return {
        "total_analyzed": total_analyzed,
        "by_risk": {
            "CRITICAL": critical_count,
            "HIGH": high_count,
            "MEDIUM": medium_count,
            "LOW": low_count
        },
        "last_updated": datetime.now().isoformat()
    }


@router.get("/analytics/top-worst")
async def get_top_worst_tokens(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
) -> List[Dict]:
    """Получает топ токенов с наибольшим риском с пагинацией"""
    client = await get_redis_client()
    
    keys = await client.keys("history:*")
    
    tokens = []
    for key in keys:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        mint = key.replace("history:", "")
        history = await client.get(key)
        if history:
            import json
            import gzip
            try:
                decompressed = gzip.decompress(history)
                data = json.loads(decompressed.decode('utf-8'))
                risk_score = data.get("risk_assessment", {}).get("score", 0)
                risk_level = data.get("risk_assessment", {}).get("level", "UNKNOWN")
                summary = data.get("summary", {})
                
                tokens.append({
                    "token_mint": mint,
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "analyzed_at": data.get("analyzed_at", ""),
                    "total_holders": summary.get("total_holders", 0),
                    "real_holders": summary.get("real_holders", 0),
                    "bots_count": summary.get("bots_count", 0)
                })
            except:
                pass
    
    # Сортируем по риску
    tokens.sort(key=lambda x: x["risk_score"], reverse=True)
    
    # Пагинация
    return tokens[offset:offset + limit]