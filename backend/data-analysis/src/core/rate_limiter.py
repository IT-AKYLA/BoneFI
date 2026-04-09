# data-analysis/src/core/rate_limiter.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
import time
import asyncio
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiter с защитой от ошибок"""
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.clients: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0))
        self._lock = asyncio.Lock()
    
    async def dispatch(self, request: Request, call_next):
        # Пропускаем health, ready, docs эндпоинты
        skip_paths = ["/health", "/ready", "/docs", "/openapi.json", "/redoc"]
        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)
        
        client_ip = request.client.host if request.client else "unknown"
        
        try:
            async with self._lock:
                count, window_start = self.clients[client_ip]
                now = time.time()
                
                if now - window_start > 60:
                    count = 0
                    window_start = now
                
                if count >= self.requests_per_minute:
                    logger.warning(f"Rate limit exceeded for {client_ip}")
                    raise HTTPException(status_code=429, detail="Too many requests")
                
                self.clients[client_ip] = (count + 1, window_start)
            
            response = await call_next(request)
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            # При ошибке rate limiter'а пропускаем запрос
            logger.error(f"Rate limiter error for {client_ip}: {e}")
            return await call_next(request)