# data-management/src/api/main.py
import os
import uuid
import hashlib
import asyncio
import gzip
import json
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Header
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..collectors.solana_collector import SolanaCollector
from ..db import get_redis_client, RedisCache, CacheKeys
from ..queue.queue_manager import enqueue_collection, get_queue_status
from ..middleware.rate_limit import RateLimitMiddleware


TOKENS_CACHE_TTL = 30

# Кэш для токенов
tokens_cache = {}
tokens_cache_time = {}

stats_cache = {}
stats_cache_time = {}

batch_jobs: Dict[str, dict] = {}

app = FastAPI(
    title="Data Management API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limit middleware
app.add_middleware(RateLimitMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
PUBLIC_MAX_SIGNATURES = int(os.getenv("PUBLIC_MAX_SIGNATURES", "100000"))


class CollectRequest(BaseModel):
    token_mint: str
    force: bool = False
    collect_mode: Optional[str] = None
    early_limit: Optional[int] = None


class BatchCollectRequest(BaseModel):
    tokens: List[str]
    force: bool = False
    collect_mode: Optional[str] = None
    early_limit: Optional[int] = None
    delay_seconds: float = 1.0


class BatchCollectResponse(BaseModel):
    total: int
    queued: List[str]
    failed: List[str]
    job_id: str


class TokenResponse(BaseModel):
    token_mint: str
    total_transactions: int
    total_signatures: int
    success_rate: float
    collected_at: str


def verify_admin(api_key: str = Header(..., alias="X-API-Key")):
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="Admin API key not configured")
    
    incoming_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    if incoming_hash != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return True


def get_max_signatures(is_admin: bool = False) -> int:
    if is_admin:
        return 10000000
    return PUBLIC_MAX_SIGNATURES


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return FileResponse("static/docs.html")


@app.on_event("startup")
async def startup_event():
    import json
    openapi_spec = app.openapi()
    with open("openapi.json", "w") as f:
        json.dump(openapi_spec, f, indent=2)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "data-management"}


@app.get("/stats")
async def get_stats(request: Request, api_key: Optional[str] = Header(None, alias="X-API-Key")):
    now = datetime.now()
    if stats_cache and (now - stats_cache_time.get("stats", now)).seconds < 30:
        return stats_cache["stats"]
    
    is_admin = False
    if api_key:
        try:
            verify_admin(api_key)
            is_admin = True
        except HTTPException:
            pass
    
    client = await get_redis_client()
    
    keys = await client.keys(f"{CacheKeys.TOKEN_PREFIX}*")
    total_size = 0
    
    for key in keys:
        data = await client.get(key)
        if data:
            total_size += len(data)
    
    info = await client.info("memory")
    
    result = {
        "tokens_count": len(keys),
        "redis_memory_mb": round(int(info.get("used_memory", 0)) / 1024 / 1024, 2),
        "compressed_data_mb": round(total_size / 1024 / 1024, 2),
        "redis_version": info.get("redis_version")
    }
    
    if is_admin:
        keys_all = await client.keys("*")
        result["total_keys"] = len(keys_all)
        result["max_signatures_allowed"] = "unlimited"
    else:
        result["max_signatures_allowed"] = PUBLIC_MAX_SIGNATURES
        
    stats_cache["stats"] = result
    stats_cache_time["stats"] = now
    return result


@app.get("/tokens", response_model=List[TokenResponse])
async def list_tokens(request: Request, limit: int = 20):
    """Список всех токенов (читаем ТОЛЬКО метаданные, без распаковки)"""
    cache_key = f"tokens:{limit}"
    now = datetime.now()
    
    if cache_key in tokens_cache and (now - tokens_cache_time.get(cache_key, now)).seconds < TOKENS_CACHE_TTL:
        return tokens_cache[cache_key]
    
    client = await get_redis_client()
    
    # Читаем ТОЛЬКО метаданные (быстро!)
    keys = await client.keys(f"{CacheKeys.META_PREFIX}*")
    keys = keys[:min(limit, len(keys))]
    
    tokens = []
    for key in keys:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        mint = key.replace(CacheKeys.META_PREFIX, "")
        
        compressed = await client.get(key)
        if compressed:
            try:
                decompressed = gzip.decompress(compressed)
                metadata = json.loads(decompressed.decode('utf-8'))
                
                tokens.append(TokenResponse(
                    token_mint=mint,
                    total_transactions=metadata.get("total_transactions", 0),
                    total_signatures=metadata.get("total_signatures", 0),
                    success_rate=metadata.get("success_rate", 0),
                    collected_at=metadata.get("collected_at", "")
                ))
            except Exception as e:
                print(f"Error reading metadata for {mint}: {e}")
                continue
    
    tokens_cache[cache_key] = tokens
    tokens_cache_time[cache_key] = now
    
    return tokens


@app.get("/token/{mint}")
async def get_token(request: Request, mint: str):
    client = await get_redis_client()
    cache = RedisCache(client)
    
    key = CacheKeys.token_key(mint)
    data = await cache.get_json(key)
    
    if not data:
        raise HTTPException(status_code=404, detail="Token not found")
    
    return {
        "token_mint": mint,
        "total_transactions": data.get("total_transactions", 0),
        "total_signatures": data.get("total_signatures", 0),
        "success_rate": data.get("success_rate", 0),
        "collection_time_seconds": data.get("collection_time_seconds", 0),
        "collected_at": data.get("collected_at"),
        "token_info": data.get("token_info", {}),
        "collect_mode": data.get("collect_mode", "latest"),
        "collect_limit": data.get("collect_limit", PUBLIC_MAX_SIGNATURES)
    }


@app.get("/token/{mint}/compressed")
async def get_compressed_token(request: Request, mint: str):
    client = await get_redis_client()
    
    key = CacheKeys.token_key(mint)
    compressed_data = await client.get(key)
    
    if not compressed_data:
        raise HTTPException(status_code=404, detail="Token not found")
    
    return Response(
        content=compressed_data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={mint}.json.gz",
            "Content-Encoding": "gzip",
            "X-Token-Mint": mint
        }
    )


@app.post("/collect")
async def collect_token(
    request: Request, 
    collect_req: CollectRequest, 
    api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    is_admin = False
    if api_key:
        try:
            verify_admin(api_key)
            is_admin = True
        except HTTPException:
            pass
    
    max_signatures = get_max_signatures(is_admin)
    
    if not is_admin and collect_req.force:
        raise HTTPException(status_code=403, detail="Force collection requires admin privileges")
    
    collect_mode = collect_req.collect_mode
    early_limit = collect_req.early_limit
    
    if collect_mode and collect_mode not in ["latest", "earliest"]:
        raise HTTPException(status_code=400, detail="collect_mode must be 'latest' or 'earliest'")
    
    job_id = enqueue_collection(
        token_mint=collect_req.token_mint,
        force=collect_req.force,
        collect_mode=collect_mode,
        early_limit=early_limit,
        max_signatures=max_signatures
    )
    
    return {
        "status": "queued",
        "job_id": job_id,
        "token_mint": collect_req.token_mint,
        "collect_mode": collect_mode or "default",
        "early_limit": early_limit if collect_mode == "earliest" else None,
        "max_signatures": max_signatures if not is_admin else "unlimited",
        "admin_mode": is_admin
    }


@app.get("/queue/status")
async def queue_status(request: Request):
    return get_queue_status()


@app.delete("/token/{mint}")
async def delete_token(request: Request, mint: str, api_key: str = Header(..., alias="X-API-Key")):
    verify_admin(api_key)
    
    client = await get_redis_client()
    cache = RedisCache(client)
    
    # Удаляем полные данные
    key = CacheKeys.token_key(mint)
    await cache.delete(key)
    
    # Удаляем метаданные
    await cache.delete(CacheKeys.meta_key(mint))
    
    # Инвалидируем кэш списка токенов
    tokens_cache.clear()
    tokens_cache_time.clear()
    
    return {"status": "deleted", "token_mint": mint}


@app.post("/collect/batch", response_model=BatchCollectResponse)
async def collect_tokens_batch(
    request: Request,
    batch_req: BatchCollectRequest,
    background_tasks: BackgroundTasks,
    api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    is_admin = False
    if api_key:
        try:
            verify_admin(api_key)
            is_admin = True
        except HTTPException:
            pass
    
    if not is_admin and len(batch_req.tokens) > 10:
        raise HTTPException(status_code=403, detail="Batch size limited to 10 tokens for non-admin users")
    
    if not is_admin and batch_req.force:
        raise HTTPException(status_code=403, detail="Force collection requires admin privileges")
    
    if batch_req.collect_mode and batch_req.collect_mode not in ["latest", "earliest"]:
        raise HTTPException(status_code=400, detail="collect_mode must be 'latest' or 'earliest'")
    
    max_signatures = get_max_signatures(is_admin)
    job_id = str(uuid.uuid4())[:8]
    
    batch_jobs[job_id] = {
        "status": "running",
        "total": len(batch_req.tokens),
        "completed": 0,
        "success": [],
        "failed": [],
        "started_at": datetime.now().isoformat()
    }
    
    async def run_batch_collection(
        tokens: List[str],
        force: bool,
        mode: Optional[str],
        limit: Optional[int],
        delay: float,
        job_id: str,
        max_sig: int
    ):
        results = {"success": [], "failed": []}
        
        for idx, token_mint in enumerate(tokens):
            print(f"\n{'='*60}")
            print(f"Processing [{idx+1}/{len(tokens)}]: {token_mint}")
            print(f"{'='*60}")
            
            try:
                collector = SolanaCollector(collect_mode=mode, early_limit=limit)
                if mode == "latest":
                    if limit and limit > 0:
                        collector.max_signatures = limit
                    else:
                        collector.max_signatures = max_sig
                else:
                    if limit and limit > 0:
                        collector.max_signatures = limit
                        collector.early_limit = limit
                    else:
                        collector.max_signatures = max_sig
                        collector.early_limit = max_sig
                
                async with collector:
                    success, data = await collector.collect(token_mint, force=force)
                    
                    if success:
                        client = await get_redis_client()
                        cache = RedisCache(client)
                        
                        # Сохраняем полные данные
                        key = CacheKeys.token_key(token_mint)
                        await cache.set_json(key, data, ttl=86400)
                        
                        metadata = {
                            "total_transactions": data.get("total_transactions", 0),
                            "total_signatures": data.get("total_signatures", 0),
                            "success_rate": data.get("success_rate", 0),
                            "collected_at": data.get("collected_at", ""),
                            "token_info": data.get("token_info", {}),
                            "collection_time_seconds": data.get("collection_time_seconds", 0)
                        }
                        await cache.set_json(CacheKeys.meta_key(token_mint), metadata, ttl=86400)
                        
                        results["success"].append(token_mint)
                        print(f"✅ Success: {token_mint} ({data.get('total_transactions', 0)} txs)")
                    else:
                        results["failed"].append(token_mint)
                        print(f"❌ Failed: {token_mint}")
                        
            except Exception as e:
                results["failed"].append(token_mint)
                print(f"❌ Error: {token_mint} - {e}")
            
            batch_jobs[job_id]["completed"] = idx + 1
            batch_jobs[job_id]["success"] = results["success"]
            batch_jobs[job_id]["failed"] = results["failed"]
            
            if idx < len(tokens) - 1:
                await asyncio.sleep(delay)
        
        batch_jobs[job_id]["status"] = "completed"
        batch_jobs[job_id]["finished_at"] = datetime.now().isoformat()
        
        print(f"\n{'='*60}")
        print(f"Batch {job_id} completed: {len(results['success'])} success, {len(results['failed'])} failed")
        print(f"{'='*60}\n")
    
    background_tasks.add_task(
        run_batch_collection,
        batch_req.tokens,
        batch_req.force,
        batch_req.collect_mode,
        batch_req.early_limit,
        batch_req.delay_seconds,
        job_id,
        max_signatures
    )
    
    return BatchCollectResponse(
        total=len(batch_req.tokens),
        queued=batch_req.tokens,
        failed=[],
        job_id=job_id
    )


@app.get("/collect/batch/{job_id}/status")
async def get_batch_status(request: Request, job_id: str):
    if job_id not in batch_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return batch_jobs[job_id]


@app.get("/collect/batch/list")
async def list_batch_jobs(request: Request, api_key: Optional[str] = Header(None, alias="X-API-Key")):
    is_admin = False
    if api_key:
        try:
            verify_admin(api_key)
            is_admin = True
        except HTTPException:
            pass
    
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return {
        "jobs": batch_jobs,
        "total": len(batch_jobs)
    }