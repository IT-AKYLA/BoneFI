# data-analysis/src/api/routes/docs.py
from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter()

DOCS_PATH = Path(__file__).parent.parent.parent / "static" / "docs.html"


@router.get("/docs", include_in_schema=False)
async def get_docs():
    """Главная документация API"""
    if not DOCS_PATH.exists():
        return FileResponse("static/docs.html", status_code=404)
    return FileResponse(DOCS_PATH)


@router.get("/api/docs", include_in_schema=False)
async def get_api_docs():
    return await get_docs()