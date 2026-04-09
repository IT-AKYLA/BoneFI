# data-management/src/middleware/rate_limit.py
import time
import redis
import os
import hashlib
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
RATE_LIMIT_DEFAULT = int(os.getenv("RATE_LIMIT_DEFAULT", "100"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


class RateLimiter:
    def __init__(self):
        self.redis = None
        self._connect_redis()
        self.default_limit = RATE_LIMIT_DEFAULT
        self.default_window = RATE_LIMIT_WINDOW
    
    def _connect_redis(self):
        try:
            self.redis = redis.from_url(REDIS_URL, decode_responses=True)
        except Exception as e:
            print(f"Redis connection failed: {e}, using in-memory fallback")
            self.redis = None
    
    def check(self, key: str, limit: int = None, window: int = None) -> tuple:
        limit = limit or self.default_limit
        window = window or self.default_window
        
        if self.redis:
            now = int(time.time())
            window_key = f"rate_limit:{key}:{now // window}"
            current = self.redis.get(window_key)
            
            if current is None:
                self.redis.setex(window_key, window, 1)
                return True, limit - 1
            
            current = int(current)
            if current < limit:
                self.redis.incr(window_key)
                return True, limit - current - 1
            return False, 0
        else:
            return self._check_memory(key, limit, window)
    
    def _check_memory(self, key: str, limit: int, window: int) -> tuple:
        now = int(time.time())
        if not hasattr(self, '_memory_store'):
            self._memory_store = {}
        
        window_key = f"{key}:{now // window}"
        current = self._memory_store.get(window_key, 0)
        
        if current < limit:
            self._memory_store[window_key] = current + 1
            return True, limit - current - 1
        return False, 0

rate_limiter = RateLimiter()

class RateLimitMiddleware(BaseHTTPMiddleware):
    ENDPOINT_LIMITS = {
        "/tokens": (50, 60),
        "/token/": (30, 60),
        "/token/.*/compressed": (100, 60),
        "/collect": (50, 60),
        "/collect/batch": (5, 60),
        "/collect/batch/.*/status": (60, 60),
        "/stats": (20, 60),
        "/health": (30, 60),
        "/queue/status": (30, 60),
    }
    DEFAULT_LIMIT = (30, 60)
    
    async def dispatch(self, request: Request, call_next):
        # Проверяем админ-ключ для обхода лимитов
        api_key = request.headers.get("X-API-Key")
        
        if ADMIN_API_KEY and api_key:
            incoming_hash = hashlib.sha256(api_key.encode()).hexdigest()
            if incoming_hash == ADMIN_API_KEY:
                # Админ, пропускаем лимиты
                return await call_next(request)
        
        # Применяем лимиты для обычных пользователей
        path = request.url.path
        limit, window = self.DEFAULT_LIMIT
        
        for endpoint, (l, w) in self.ENDPOINT_LIMITS.items():
            if path.startswith(endpoint) or path == endpoint:
                limit, window = l, w
                break
        
        client_ip = request.client.host
        key = f"{client_ip}:{path}"
        
        allowed, remaining = rate_limiter.check(key, limit, window)
        
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Limit: {limit} requests per {window} seconds."
            )
        
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(window)
        
        return response