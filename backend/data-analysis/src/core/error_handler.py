# data-analysis/src/core/error_handler.py
import logging
import traceback
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """Глобальный обработчик исключений для всех эндпоинтов"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            return await self._handle_exception(request, e)
    
    async def _handle_exception(self, request: Request, exc: Exception) -> JSONResponse:
        error_type = type(exc).__name__
        error_msg = str(exc)
        
        logger.error(f"Unhandled exception on {request.method} {request.url.path}")
        logger.error(f"Error type: {error_type}")
        logger.error(f"Error message: {error_msg}")
        logger.error(traceback.format_exc())
        
        # Fix: check if status_code exists and is not None
        if hasattr(exc, 'status_code') and exc.status_code is not None:
            status_code = exc.status_code
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": {
                    "type": error_type,
                    "message": error_msg if status_code != 500 else "Internal server error",
                    "path": request.url.path,
                    "method": request.method
                }
            }
        )