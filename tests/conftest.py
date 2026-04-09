import pytest
import asyncio
import aiohttp
import sys
from typing import AsyncGenerator

# Платформа
IS_WINDOWS = sys.platform == 'win32'

# Конфиги сервисов
ANALYSIS_API_URL = "http://localhost:8000"
MANAGEMENT_API_URL = "http://localhost:8001"


@pytest.fixture(scope="session")
def event_loop():
    """Создает event loop для всех тестов"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def analysis_client() -> AsyncGenerator:
    """HTTP клиент для Analysis API"""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
async def management_client() -> AsyncGenerator:
    """HTTP клиент для Management API"""
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def is_windows():
    """Платформа Windows"""
    return IS_WINDOWS


@pytest.fixture
def test_token():
    """Тестовый токен (маленький, из твоего списка)"""
    return "5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump"


@pytest.fixture
def scam_token():
    """Скам-токен для тестов"""
    return "CyanDgP3THbfWCPg5P7mRS8Dd4NvwN2agdjmi17Ppump"


def pytest_configure(config):
    """Регистрация маркеров"""
    config.addinivalue_line("markers", "integration: Integration tests requiring running services")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow tests")