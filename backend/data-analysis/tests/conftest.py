import pytest
import sys
import random
from pathlib import Path
from unittest.mock import AsyncMock

# Добавляем путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mock_redis():
    """Мок Redis клиента"""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock(return_value=True)
    mock.keys = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_cache(mock_redis):
    """Мок кэша"""
    from core.database import RedisCache
    return RedisCache(mock_redis)


@pytest.fixture
def mock_token_data():
    """Мок данных токена"""
    return {
        "token_mint": "MockToken111111111111111111111111111111111",
        "token_info": {"decimals": 6, "supply": 1000000000000},
        "transactions": []
    }


@pytest.fixture
def analyzer_with_mock_data(mock_token_data):
    """Анализатор с мок-данными"""
    from services.analyzer import TokenAnalyzer
    return TokenAnalyzer(mock_token_data, use_cache=False)


@pytest.fixture
def sample_transactions():
    """Пример транзакций для тестов"""
    base_time = 1700000000
    transactions = []
    
    for i in range(100):
        tx = {
            "blockTime": base_time + i * random.randint(1, 30),
            "meta": {
                "preTokenBalances": [],
                "postTokenBalances": [
                    {
                        "mint": "MockToken",
                        "owner": f"Wallet_{random.randint(1, 20)}",
                        "uiTokenAmount": {"amount": str(random.randint(1000, 10000000)), "decimals": 6}
                    }
                ]
            },
            "transaction": {
                "message": {
                    "accountKeys": [
                        f"Wallet_{random.randint(1, 20)}",
                        random.choice(["pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"])
                    ]
                }
            }
        }
        transactions.append(tx)
    
    return transactions


@pytest.fixture
def analyzer_with_transactions(sample_transactions):
    """Анализатор с тестовыми транзакциями"""
    from services.analyzer import TokenAnalyzer
    
    data = {
        "token_mint": "TestToken",
        "token_info": {"decimals": 6, "supply": 1000000000000},
        "transactions": sample_transactions
    }
    return TokenAnalyzer(data, use_cache=False)


@pytest.fixture
def analyzer():
    """Алиас для analyzer_with_transactions (для обратной совместимости)"""
    return analyzer_with_transactions


@pytest.fixture
def scam_indicators_data():
    """Данные со скам-паттернами для тестов"""
    from services.analyzer import TokenAnalyzer
    
    base_time = 1700000000
    transactions = []
    
    # Инсайдерские покупки (первые 5 минут)
    for i in range(50):
        transactions.append({
            "blockTime": base_time + i * 2,
            "meta": {
                "preTokenBalances": [],
                "postTokenBalances": [{
                    "mint": "ScamToken",
                    "owner": f"Insider{i}",
                    "uiTokenAmount": {"amount": "10000000", "decimals": 6}
                }]
            },
            "transaction": {
                "message": {
                    "accountKeys": [f"Insider{i}", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"]
                }
            }
        })
    
    # Бот-кластер (массовые покупки в одно время)
    cluster_time = base_time + 300
    for i in range(100):
        transactions.append({
            "blockTime": cluster_time + (i % 5),
            "meta": {
                "postTokenBalances": [{
                    "mint": "ScamToken",
                    "owner": f"ClusterBot{i}",
                    "uiTokenAmount": {"amount": "500000", "decimals": 6}
                }]
            },
            "transaction": {
                "message": {
                    "accountKeys": [f"ClusterBot{i}", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"]
                }
            }
        })
    
    data = {
        "token_mint": "ScamToken",
        "token_info": {"decimals": 6, "supply": 1000000000000},
        "transactions": transactions
    }
    return TokenAnalyzer(data, use_cache=False)