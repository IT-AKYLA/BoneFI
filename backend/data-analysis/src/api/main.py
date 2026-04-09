# data-analysis/src/api/main.py
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import logging
import traceback
import sys

from ..core.rate_limiter import RateLimitMiddleware
from ..core.error_handler import GlobalExceptionMiddleware
from ..services import setup_numpy_encoder  # ✅ ДОБАВИТЬ ИМПОРТ
# from ..services.scheduler import scheduler
scheduler = None


from .routes import (
    analysis_router,
    tokens_router,
    charts_router,
    bubblemap_router,
    token_details_router,
    docs_router,
    history_router,
    scheduler_router
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ========== ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ ==========
async def global_exception_handler(request: Request, exc: Exception):
    """Глобальный обработчик всех исключений"""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}")
    logger.error(f"Exception: {type(exc).__name__}: {str(exc)}")
    logger.error(traceback.format_exc())
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "type": type(exc).__name__,
                "message": "Internal server error",
                "path": request.url.path,
                "method": request.method
            }
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Обработчик HTTP исключений"""
    logger.warning(f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "type": "HTTPException",
                "message": exc.detail,
                "path": request.url.path,
                "method": request.method
            }
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application...")
    
    scheduler_task = None
    # try:
    #     await scheduler.initialize()
    #     scheduler_task = asyncio.create_task(scheduler.run_forever())
    #     logger.info("Scheduler started")
    # except Exception as e:
    #     logger.error(f"Failed to start scheduler: {e}")
    
    yield
    
    logger.info("Shutting down...")
    if scheduler:
        scheduler.stop()
    
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()
        try:
            await asyncio.wait_for(scheduler_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    
    await asyncio.sleep(0.5)
    logger.info("Shutdown complete")


# ========== СОЗДАНИЕ ПРИЛОЖЕНИЯ ==========
app = FastAPI(
    title="Data Analysis API", 
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Регистрируем обработчики исключений (ДО middleware)
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiter
app.add_middleware(RateLimitMiddleware)

# Глобальный middleware для ошибок
app.add_middleware(GlobalExceptionMiddleware)

# ✅✅✅ ГЛОБАЛЬНАЯ НАСТРОЙКА ДЛЯ NUMPY ТИПОВ (ДОБАВИТЬ СЮДА) ✅✅✅
setup_numpy_encoder(app)
logger.info("✅ Numpy encoder configured")


# ========== РЕГИСТРАЦИЯ РОУТЕРОВ ==========
try:
    app.include_router(analysis_router, prefix="/api", tags=["analysis"])
    app.include_router(tokens_router, prefix="/api", tags=["tokens"])
    app.include_router(charts_router, prefix="/api", tags=["charts"])
    app.include_router(bubblemap_router, prefix="/api", tags=["bubblemap"])
    app.include_router(token_details_router, prefix="/api", tags=["token"])
    app.include_router(history_router, prefix="/api", tags=["history"])
    app.include_router(scheduler_router, prefix="/api", tags=["scheduler"])
    app.include_router(docs_router, tags=["documentation"])
    logger.info("✅ All routers registered successfully")
except Exception as e:
    logger.error(f"❌ Failed to register routers: {e}")


# ========== БАЗОВЫЕ ЭНДПОИНТЫ ==========
@app.get("/health")
async def health():
    try:
        from ..core.database import get_redis_client
        client = await get_redis_client()
        await client.ping()
        return {"status": "ok", "service": "data-analysis", "redis": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "degraded", "service": "data-analysis", "redis": "disconnected"}


@app.get("/ready")
async def ready():
    return {"status": "ready", "service": "data-analysis"}