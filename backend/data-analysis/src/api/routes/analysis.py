# data-analysis/src/api/routes/analysis.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
import asyncio
import uuid
from typing import Dict, Optional
from datetime import datetime

from ...core.database import RedisCache, get_redis_client
from ...services.analyzer import TokenAnalyzer

router = APIRouter()

# Хранилище результатов анализа (в реальном проекте используй Redis)
analysis_tasks: Dict[str, dict] = {}


@router.get("/analyze/{mint}")
async def analyze_token_async(
    mint: str, 
    save_history: bool = False,
    include_revolutionary: bool = Query(True, description="Включить революционные метрики"),
    background_tasks: BackgroundTasks = None
) -> Dict:
    """
    Асинхронный анализ токена (возвращает task_id)
    
    - include_revolutionary: включает 5 новых революционных метрик (по умолчанию True)
    """
    client = await get_redis_client()
    cache = RedisCache(client)
    
    data = await cache.get_token(mint)
    if not data:
        raise HTTPException(status_code=404, detail="Token not found in cache")
    
    task_id = str(uuid.uuid4())[:8]
    
    analysis_tasks[task_id] = {
        "status": "processing",
        "started_at": datetime.now().isoformat(),
        "token_mint": mint,
        "result": None,
        "error": None,
        "include_revolutionary": include_revolutionary
    }
    
    def run_analysis():
        try:
            analyzer = TokenAnalyzer(data)
            
            # Получаем полный анализ
            result = analyzer.get_full_analysis(save_history=save_history)
            
            # Добавляем революционные метрики если нужно
            if include_revolutionary and hasattr(analyzer, 'get_revolutionary_risk_score'):
                result["revolutionary_metrics"] = analyzer.get_revolutionary_risk_score()
                result["temporal_entropy"] = analyzer.get_temporal_entropy()
                result["anti_fragmentation"] = analyzer.get_anti_fragmentation()
                result["domino_effect"] = analyzer.get_domino_effect()
                result["migration_footprint"] = analyzer.get_migration_footprint()
                result["herding_index"] = analyzer.get_herding_index()
                result["analysis_mode"] = "full_with_revolutionary"
            
            analysis_tasks[task_id]["status"] = "completed"
            analysis_tasks[task_id]["result"] = result
            analysis_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        except Exception as e:
            analysis_tasks[task_id]["status"] = "failed"
            analysis_tasks[task_id]["error"] = str(e)
    
    background_tasks.add_task(asyncio.to_thread, run_analysis)
    
    return {
        "task_id": task_id,
        "status": "processing",
        "token_mint": mint,
        "include_revolutionary": include_revolutionary,
        "message": "Analysis started. Use /api/analyze/result/{task_id} to get results"
    }


@router.get("/analyze/result/{task_id}")
async def get_analysis_result(task_id: str) -> Dict:
    """Получает результат анализа по task_id"""
    if task_id not in analysis_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = analysis_tasks[task_id]
    
    if task["status"] == "processing":
        return {
            "task_id": task_id,
            "status": "processing",
            "message": "Analysis still in progress"
        }
    elif task["status"] == "failed":
        result = {
            "task_id": task_id,
            "status": "failed",
            "error": task["error"]
        }
        # Удаляем после получения
        del analysis_tasks[task_id]
        return result
    else:
        result = {
            "task_id": task_id,
            "status": "completed",
            "result": task["result"]
        }
        # Удаляем после получения
        del analysis_tasks[task_id]
        return result


@router.get("/analyze/sync/{mint}")
async def analyze_token_sync(
    mint: str, 
    save_history: bool = False,
    include_revolutionary: bool = Query(True, description="Включить революционные метрики")
) -> Dict:
    """
    Синхронный анализ (только для маленьких токенов, может зависнуть)
    """
    client = await get_redis_client()
    cache = RedisCache(client)
    
    data = await cache.get_token(mint)
    if not data:
        raise HTTPException(status_code=404, detail="Token not found in cache")
    
    try:
        analyzer = TokenAnalyzer(data)
        result = analyzer.get_full_analysis(save_history=save_history)
        
        # Добавляем революционные метрики если нужно
        if include_revolutionary and hasattr(analyzer, 'get_revolutionary_risk_score'):
            result["revolutionary_metrics"] = analyzer.get_revolutionary_risk_score()
            result["temporal_entropy"] = analyzer.get_temporal_entropy()
            result["anti_fragmentation"] = analyzer.get_anti_fragmentation()
            result["domino_effect"] = analyzer.get_domino_effect()
            result["migration_footprint"] = analyzer.get_migration_footprint()
            result["herding_index"] = analyzer.get_herding_index()
            result["analysis_mode"] = "full_with_revolutionary"
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))