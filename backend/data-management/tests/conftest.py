import pytest
import asyncio
import redis.asyncio as redis
from src.db.redis_client import RedisCache
from src.collectors.solana_collector import SolanaCollector

# Тестовые токены (из твоего списка, с небольшим количеством транзакций)
TEST_TOKENS = {
    "small": "5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump",  # 1.9K tx
    "medium": "CyanDgP3THbfWCPg5P7mRS8Dd4NvwN2agdjmi17Ppump",  # 4.8K tx
}


@pytest.fixture
async def redis_client():
    """Redis клиент для тестов"""
    client = await redis.from_url("redis://localhost:6379", decode_responses=True)
    yield client
    await client.close()


@pytest.fixture
async def cache(redis_client):
    """Кэш для тестов"""
    return RedisCache(redis_client)


@pytest.fixture
def collector():
    """Коллектор для тестов"""
    return SolanaCollector(
        collect_mode="latest",
        early_limit=5000  # Маленький лимит для тестов
    )


@pytest.fixture
def mock_signatures():
    """Мок-сигнатуры для тестов"""
    return [f"signature_{i}" for i in range(100)]


@pytest.fixture
def mock_transaction():
    """Мок-транзакция"""
    return {
        "blockTime": 1700000000,
        "meta": {
            "preTokenBalances": [],
            "postTokenBalances": []
        },
        "transaction": {
            "message": {
                "accountKeys": ["test_wallet", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"]
            }
        }
    }