# data-analysis/src/api/routes/status.py
from fastapi import APIRouter, Request
from ..core.rate_limiter import rate_limiter

router = APIRouter()


@router.get("/rate-limit-status")
async def get_rate_limit_status(request: Request):
    client_ip = request.client.host
    return {
        "client_ip": client_ip,
        "limit": rate_limiter.default_limit,
        "window_seconds": rate_limiter.default_window,
        "message": f"Maximum {rate_limiter.default_limit} requests per {rate_limiter.default_window} seconds"
    }