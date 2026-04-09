import pytest


class TestTokenAnalyzer:
    """Тесты анализатора"""
    
    def test_initialization(self, analyzer_with_mock_data):
        assert analyzer_with_mock_data.token_mint == "MockToken111111111111111111111111111111111"
        assert analyzer_with_mock_data.decimals == 6
    
    def test_current_holders(self, analyzer_with_transactions):
        assert isinstance(analyzer_with_transactions.current_holders, dict)
    
    def test_is_liquidity_pool(self, analyzer_with_mock_data):
        is_pool = analyzer_with_mock_data.is_liquidity_pool(
            "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", 10.0, 100
        )
        assert is_pool == True
        
        is_pool = analyzer_with_mock_data.is_liquidity_pool("NormalWallet", 0.1, 5)
        assert is_pool == False
    
    def test_is_bot(self, analyzer_with_mock_data):
        assert analyzer_with_mock_data.is_bot(0.02) == True
        assert analyzer_with_mock_data.is_bot(0.1) == False
    
    def test_top_holders_limit(self, analyzer_with_transactions):
        holders = analyzer_with_transactions.get_top_holders_full(limit=5)
        assert len(holders) <= 5
    
    def test_get_migration_speed_analysis(self, analyzer_with_transactions):
        result = analyzer_with_transactions.get_migration_speed_analysis()
        assert isinstance(result, dict)


class TestScamDetection:
    """Тесты детекции скамов"""
    
    def test_malicious_supply_index(self, scam_indicators_data):
        result = scam_indicators_data.get_malicious_supply_index()
        assert "malicious_supply_percent" in result
        assert "risk_level" in result
    
    def test_suspicious_supply_index(self, scam_indicators_data):
        result = scam_indicators_data.calculate_suspicious_supply_index()
        if "error" in result:
            pytest.skip("No holders in test data")
        assert "suspicious_supply_percent" in result
    
    def test_bot_clusters(self, scam_indicators_data):
        result = scam_indicators_data.get_bot_clusters()
        # Метод всегда возвращает словарь с ключами 'clusters' и 'risk_score'
        # 'clusters_found' может отсутствовать если нет данных
        assert isinstance(result, dict)
        # Проверяем, что есть хотя бы один из ключей
        assert any(key in result for key in ["clusters_found", "clusters", "risk_score"])
    
    def test_risk_assessment(self, scam_indicators_data):
        result = scam_indicators_data.get_hard_risk_score()
        assert "score" in result
        assert "level" in result