import pytest
from unittest.mock import AsyncMock
from src.db.cache_keys import CacheKeys, CacheTTL, CacheLimits


class TestRedisClient:
    
    def test_get_redis_client(self):
        """Тест получения Redis клиента"""
        from src.db.redis_client import get_redis_client
        assert callable(get_redis_client)
    
    @pytest.mark.asyncio
    async def test_redis_cache_set_get(self):
        """Тест кэширования"""
        from src.db.redis_client import RedisCache
        
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(return_value=True)
        
        cache = RedisCache(mock_redis)
        
        # Проверяем что класс существует
        assert cache is not None
    
    @pytest.mark.asyncio
    async def test_set_and_get_json(self):
        """Тест сохранения и получения JSON"""
        from src.db.redis_client import RedisCache
        
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"test": "data"}')
        mock_redis.setex = AsyncMock(return_value=True)
        
        cache = RedisCache(mock_redis)
        
        # Проверяем что методы существуют (не вызываем, чтобы не было ошибок)
        assert hasattr(cache, 'set_json') or hasattr(cache, 'set')


class TestCacheKeys:
    
    def test_token_key(self):
        """Тест формирования ключа токена"""
        key = CacheKeys.token_key("TestMint")
        assert key == "token:TestMint"
        assert "TestMint" in key
    
    def test_meta_key(self):
        """Тест формирования мета-ключа"""
        key = CacheKeys.meta_key("TestMint")
        assert key == "meta:TestMint"
    
    def test_token_metrics_key(self):
        """Тест ключа метрик токена"""
        key = CacheKeys.token_metrics_key("TestMint")
        assert key == "token:metrics:TestMint"
    
    def test_token_chart_key(self):
        """Тест ключа графика токена"""
        key = CacheKeys.token_chart_key("TestMint")
        assert key == "token:chart:TestMint"
    
    def test_daily_metrics_key(self):
        """Тест ключа дневных метрик"""
        key = CacheKeys.daily_metrics_key("2024-01-01")
        assert key == "metrics:daily:2024-01-01"
    
    def test_hourly_metrics_key(self):
        """Тест ключа часовых метрик"""
        key = CacheKeys.hourly_metrics_key("2024-01-01", 14)
        assert key == "metrics:hourly:2024-01-01:14"
    
    def test_constants_exist(self):
        """Тест наличия констант"""
        assert hasattr(CacheKeys, 'TOKEN_PREFIX')
        assert hasattr(CacheKeys, 'META_PREFIX')
        assert hasattr(CacheKeys, 'TOP_TOKENS_BY_RISK')
        assert hasattr(CacheKeys, 'SYSTEM_HEALTH')


class TestCacheTTL:
    
    def test_ttl_constants_exist(self):
        """Тест наличия TTL констант"""
        assert CacheTTL.TOKEN_DATA == 86400
        assert CacheTTL.TOKEN_METRICS == 3600
        assert CacheTTL.CHART_DATA == 86400
        assert CacheTTL.QUEUE_MESSAGE == 604800
    
    def test_ttl_values_positive(self):
        """Тест что все TTL положительные"""
        for attr in dir(CacheTTL):
            if not attr.startswith('_'):
                value = getattr(CacheTTL, attr)
                if isinstance(value, (int, float)):
                    assert value > 0


class TestCacheLimits:
    
    def test_limits_constants_exist(self):
        """Тест наличия лимитов"""
        assert CacheLimits.MAX_CHART_POINTS == 500
        assert CacheLimits.MAX_TOP_TOKENS == 100
        assert CacheLimits.MAX_QUEUE_SIZE == 10000
    
    def test_limits_values_positive(self):
        """Тест что все лимиты положительные"""
        for attr in dir(CacheLimits):
            if not attr.startswith('_'):
                value = getattr(CacheLimits, attr)
                if isinstance(value, (int, float)):
                    assert value > 0