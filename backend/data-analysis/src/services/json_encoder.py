import numpy as np
from functools import singledispatch
from typing import Any
import json
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


@singledispatch
def _convert_numpy(obj: Any) -> Any:
    return obj


@_convert_numpy.register
def _(obj: np.integer) -> int:
    return int(obj)


@_convert_numpy.register
def _(obj: np.floating) -> float:
    return float(obj)


@_convert_numpy.register
def _(obj: np.ndarray) -> list:
    return obj.tolist()


@_convert_numpy.register
def _(obj: np.bool_) -> bool:
    return bool(obj)


@_convert_numpy.register
def _(obj: np.void) -> None:
    return None


@_convert_numpy.register
def _(obj: np.datetime64) -> str:
    return str(obj)


@_convert_numpy.register
def _(obj: np.timedelta64) -> str:
    return str(obj)


@_convert_numpy.register
def _(obj: dict) -> dict:
    return {k: _convert_numpy(v) for k, v in obj.items()}


@_convert_numpy.register
def _(obj: list) -> list:
    return [_convert_numpy(item) for item in obj]


@_convert_numpy.register
def _(obj: tuple) -> list:
    return [_convert_numpy(item) for item in obj]


def clean_numpy(obj: Any) -> Any:
    return _convert_numpy(obj)


def numpy_encoder(obj: Any) -> Any:
    """Упрощенная версия для jsonable_encoder"""
    return clean_numpy(obj)


def safe_json_response(content: Any, status_code: int = 200) -> JSONResponse:
    """Безопасно возвращает JSONResponse с автоматической конвертацией"""
    return JSONResponse(
        content=clean_numpy(content),
        status_code=status_code
    )


class NumpyJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        return clean_numpy(obj)


def setup_numpy_encoder(app: FastAPI):
    """Настраивает FastAPI приложение для работы с numpy типами"""
    app.json_encoder = NumpyJSONEncoder
    return app