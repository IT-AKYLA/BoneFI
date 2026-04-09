# data-analysis/src/core/safe_executor.py
import asyncio
import logging
from functools import wraps
from typing import Callable, Any, Dict, Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def safe_endpoint(default_return: Any = None, log_error: bool = True):
    """
    Декоратор для безопасного выполнения эндпоинтов
    
    Args:
        default_return: Значение по умолчанию при ошибке
        log_error: Логировать ли ошибку
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except asyncio.CancelledError:
                logger.warning(f"Request cancelled for {func.__name__}")
                raise
            except Exception as e:
                if log_error:
                    logger.error(f"Error in {func.__name__}: {type(e).__name__}: {str(e)}")
                
                if default_return is not None:
                    return default_return
                
                raise HTTPException(
                    status_code=500,
                    detail=f"Internal server error in {func.__name__}: {str(e)}"
                )
        return wrapper
    return decorator


def safe_sync_endpoint(default_return: Any = None, log_error: bool = True):
    """Декоратор для синхронных эндпоинтов"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                if log_error:
                    logger.error(f"Error in {func.__name__}: {type(e).__name__}: {str(e)}")
                
                if default_return is not None:
                    return default_return
                
                raise HTTPException(
                    status_code=500,
                    detail=f"Internal server error in {func.__name__}: {str(e)}"
                )
        return wrapper
    return decorator


class SafeExecutor:
    """Безопасный исполнитель для операций с возможными ошибками"""
    
    @staticmethod
    async def run_async(coro, default: Any = None, error_msg: str = None) -> Any:
        """Безопасно выполняет асинхронную операцию"""
        try:
            return await coro
        except Exception as e:
            logger.error(f"{error_msg or 'Operation failed'}: {type(e).__name__}: {str(e)}")
            return default
    
    @staticmethod
    def run_sync(func, default: Any = None, error_msg: str = None) -> Any:
        """Безопасно выполняет синхронную операцию"""
        try:
            return func()
        except Exception as e:
            logger.error(f"{error_msg or 'Operation failed'}: {type(e).__name__}: {str(e)}")
            return default