# data-analysis/src/api/routes/scheduler.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict
import asyncio

from ...services.scheduler import scheduler

router = APIRouter()


@router.get("/scheduler/status")
async def get_scheduler_status() -> Dict:
    """Получает статус планировщика"""
    return {
        "running": scheduler.running,
        "analyzed_tokens_count": len(scheduler.analyzed_tokens),
        "last_scan_time": scheduler.last_scan_time.isoformat() if scheduler.last_scan_time else None,
        "scan_interval_minutes": scheduler.scan_interval,
        "batch_size": scheduler.batch_size
    }


@router.post("/scheduler/start")
async def start_scheduler() -> Dict:
    """Запускает планировщик вручную"""
    if scheduler.running:
        raise HTTPException(status_code=400, detail="Scheduler already running")
    
    await scheduler.start()
    return {"status": "started", "message": "Scheduler started"}


@router.post("/scheduler/stop")
async def stop_scheduler() -> Dict:
    """Останавливает планировщик"""
    if not scheduler.running:
        raise HTTPException(status_code=400, detail="Scheduler not running")
    
    await scheduler.stop()
    return {"status": "stopped", "message": "Scheduler stopped"}


@router.post("/scheduler/scan-now")
async def trigger_manual_scan(
    background_tasks: BackgroundTasks,
    force: bool = False
) -> Dict:
    """Запускает ручное сканирование"""
    # Запускаем в фоне
    background_tasks.add_task(scheduler.scan_and_analyze, force_reanalyze=force)
    return {"status": "scanning", "message": f"Manual scan triggered (force={force})"}


@router.post("/scheduler/reanalyze/{mint}")
async def reanalyze_single_token(
    mint: str,
    background_tasks: BackgroundTasks
) -> Dict:
    """Принудительно переанализирует конкретный токен"""
    background_tasks.add_task(scheduler.reanalyze_token, mint)
    return {"status": "queued", "message": f"Token {mint[:16]}... queued for reanalysis"}