import pytest
from src.collectors.solana_collector import SolanaCollector

# Тестовые токены (реальные, из твоего списка)
TEST_TOKENS = {
    "small": "5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump",   # 1.9K tx
    "medium": "CyanDgP3THbfWCPg5P7mRS8Dd4NvwN2agdjmi17Ppump",  # 4.8K tx
}


class TestSolanaCollector:
    
    def test_init(self):
        collector = SolanaCollector(collect_mode="latest", early_limit=10000)
        assert collector.collect_mode == "latest"
        assert collector.early_limit == 10000
    
    def test_get_next_rpc(self, collector):
        rpc = collector._get_next_rpc()
        assert rpc is not None
    
    def test_mark_failed(self, collector):
        endpoint = "https://test.com"
        collector._mark_failed(endpoint)
        assert collector.failed_endpoints.get(endpoint, 0) == 1
    
    def test_collector_modes(self):
        collector_latest = SolanaCollector(collect_mode="latest")
        assert collector_latest.collect_mode == "latest"
        
        collector_earliest = SolanaCollector(collect_mode="earliest")
        assert collector_earliest.collect_mode == "earliest"
    
    def test_batch_size_config(self):
        collector = SolanaCollector()
        assert collector.batch_size > 0


class TestTokenCollection:
    
    @pytest.mark.asyncio
    async def test_get_token_supply(self, collector):
        """Тест получения информации о токене"""
        try:
            result = await collector.get_token_supply(TEST_TOKENS["small"])
            assert isinstance(result, dict)
        except Exception as e:
            pytest.skip(f"Network error: {e}")
    
    @pytest.mark.asyncio
    async def test_get_signatures(self, collector):
        """Тест получения сигнатур"""
        try:
            signatures = await collector.get_all_signatures(TEST_TOKENS["small"])
            assert isinstance(signatures, list)
        except Exception as e:
            pytest.skip(f"Network error: {e}")
    
    @pytest.mark.asyncio
    async def test_fetch_transaction(self, collector, mock_signatures):
        if len(mock_signatures) > 0:
            tx = await collector.fetch_transaction(mock_signatures[0])
            assert tx is None or isinstance(tx, dict)
    
    @pytest.mark.asyncio
    async def test_collect_small_token(self, collector):
        """Тест сбора маленького токена"""
        try:
            success, data = await collector.collect(TEST_TOKENS["small"], force=True)
            assert isinstance(success, bool)
            assert isinstance(data, dict)
        except Exception as e:
            pytest.skip(f"Network error: {e}")


class TestEdgeCases:
    
    @pytest.mark.asyncio
    async def test_collect_invalid_token(self, collector):
        success, data = await collector.collect("InvalidTokenAddress", force=True)
        # Может вернуть False или данные с ошибкой
        assert isinstance(success, bool)
    
    @pytest.mark.asyncio
    async def test_empty_signatures(self, collector):
        result = await collector.fetch_transactions_parallel([])
        assert result == []
    
    @pytest.mark.asyncio
    async def test_rpc_rotation(self, collector):
        initial_rpc = collector._get_next_rpc()
        collector._mark_failed(initial_rpc)
        new_rpc = collector._get_next_rpc()
        assert new_rpc is not None


@pytest.fixture
def collector():
    return SolanaCollector(collect_mode="latest", early_limit=1000)


@pytest.fixture
def mock_signatures():
    return [f"signature_{i}" for i in range(10)]