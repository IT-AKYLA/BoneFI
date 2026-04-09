from fastapi import APIRouter, HTTPException, Query
from typing import Dict

from ...core.database import RedisCache, get_redis_client
from ...services.analyzer import TokenAnalyzer
from ...charts.combined_chart import CombinedChartGenerator
from ...services import clean_numpy

router = APIRouter()
chart_generator = CombinedChartGenerator()


@router.get("/chart/{mint}")
async def get_combined_chart(
    mint: str,
    interval_minutes: int = Query(5, ge=1, le=60),
    exclude_pools: bool = Query(True)
) -> Dict:
    client = await get_redis_client()
    cache = RedisCache(client)
    
    data = await cache.get_token(mint)
    
    if not data:
        raise HTTPException(status_code=404, detail="Token not found")
    
    analyzer = TokenAnalyzer(data)
    analyzer._ensure_initialized()

    result = chart_generator.get_chart_data(analyzer, mint, exclude_pools, interval_minutes)
    
    # Очищаем от numpy типов перед отправкой
    result = clean_numpy(result)
    
    return result