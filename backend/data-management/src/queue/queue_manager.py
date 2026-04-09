# import os
# import sys

# if sys.platform == 'win32':
#     os.environ['FORKED_BY_MULTIPROCESSING'] = '1'

# import redis
# from rq import Queue, Retry
# from rq.job import Job

# redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
# task_queue = Queue("tasks", connection=redis_conn, default_timeout=3600)


# def enqueue_collection(token_mint: str, force: bool = False, collect_mode: str = None, early_limit: int = None, max_signatures: int = None) -> str:
#     """Добавляет задачу сбора в очередь с поддержкой режимов сбора"""
    
#     def sync_wrapper():
#         import asyncio
#         from ...collectors.solana_collector import SolanaCollector
#         from ...db import get_redis_client, RedisCache, CacheKeys
        
#         async def run():
#             collector = SolanaCollector(collect_mode=collect_mode, early_limit=early_limit)
#             collector.max_signatures = max_signatures if collect_mode == "latest" else (early_limit or max_signatures or 100000)
            
#             async with collector:
#                 success, data = await collector.collect(token_mint, force=force)
#                 if success:
#                     client = await get_redis_client()
#                     cache = RedisCache(client)
#                     key = CacheKeys.token_key(token_mint)
#                     await cache.set_json(key, data, ttl=86400)
#                     return True
#             return False
        
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         try:
#             return loop.run_until_complete(run())
#         finally:
#             loop.close()
    
#     job = task_queue.enqueue(
#         sync_wrapper,
#         retry=Retry(max=3, interval=60),
#         job_timeout=3600,
#         job_id=f"collect_{token_mint}_{collect_mode or 'latest'}"
#     )
#     return job.id


# def get_queue_status() -> dict:
#     """Статус очереди"""
#     return {
#         "queued": len(task_queue),
#         "started": len(task_queue.started_job_registry),
#         "finished": len(task_queue.finished_job_registry),
#         "failed": len(task_queue.failed_job_registry),
#         "job_ids": list(task_queue.job_ids)[:20]
#     }


# def cancel_job(job_id: str) -> bool:
#     """Отменяет задачу"""
#     try:
#         job = Job.fetch(job_id, connection=redis_conn)
#         job.cancel()
#         return True
#     except Exception:
#         return False

# data-management/src/queue/queue_manager.py
import os
import sys
import uuid
import asyncio
from datetime import datetime

# Простая имитация очереди для Windows
IS_WINDOWS = sys.platform == 'win32'

if not IS_WINDOWS:
    import redis
    from rq import Queue, Retry
    from rq.job import Job
    
    redis_conn = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    task_queue = Queue("tasks", connection=redis_conn, default_timeout=3600)


def enqueue_collection(token_mint: str, force: bool = False, collect_mode: str = None, early_limit: int = None, max_signatures: int = None) -> str:
    """Добавляет задачу сбора в очередь"""
    
    async def run():
        from ...collectors.solana_collector import SolanaCollector
        from ...db import get_redis_client, RedisCache, CacheKeys
        
        collector = SolanaCollector(collect_mode=collect_mode, early_limit=early_limit)
        collector.max_signatures = max_signatures if collect_mode == "latest" else (early_limit or max_signatures or 100000)
        
        async with collector:
            success, data = await collector.collect(token_mint, force=force)
            if success:
                client = await get_redis_client()
                cache = RedisCache(client)
                key = CacheKeys.token_key(token_mint)
                await cache.set_json(key, data, ttl=86400)
                return True
        return False
    
    job_id = str(uuid.uuid4())[:8]
    
    if IS_WINDOWS:
        # На Windows запускаем синхронно
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()
        return job_id
    else:
        # На Linux используем RQ
        def sync_wrapper():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(run())
            finally:
                loop.close()
        
        job = task_queue.enqueue(
            sync_wrapper,
            retry=Retry(max=3, interval=60),
            job_timeout=3600,
            job_id=f"collect_{token_mint}_{collect_mode or 'latest'}"
        )
        return job.id


def get_queue_status() -> dict:
    """Статус очереди"""
    if IS_WINDOWS:
        return {"queued": 0, "started": 0, "finished": 0, "failed": 0, "job_ids": []}
    else:
        return {
            "queued": len(task_queue),
            "started": len(task_queue.started_job_registry),
            "finished": len(task_queue.finished_job_registry),
            "failed": len(task_queue.failed_job_registry),
            "job_ids": list(task_queue.job_ids)[:20]
        }


def cancel_job(job_id: str) -> bool:
    """Отменяет задачу"""
    if IS_WINDOWS:
        return False
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        job.cancel()
        return True
    except Exception:
        return False