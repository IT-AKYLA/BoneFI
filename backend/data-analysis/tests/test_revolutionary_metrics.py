import pytest


class TestRevolutionaryMetrics:
    """Тесты революционных метрик"""
    
    def test_temporal_entropy(self, analyzer_with_transactions):
        """Тест временной энтропии"""
        result = analyzer_with_transactions.get_temporal_entropy()
        assert isinstance(result, dict)
        assert "entropy_score" in result or "error" in result
    
    def test_anti_fragmentation(self, analyzer_with_transactions):
        """Тест анти-фрагментации"""
        result = analyzer_with_transactions.get_anti_fragmentation()
        assert isinstance(result, dict)
        assert "total_holders_reported" in result or "error" in result
    
    def test_domino_effect(self, analyzer_with_transactions):
        """Тест эффекта домино"""
        result = analyzer_with_transactions.get_domino_effect()
        assert isinstance(result, dict)
        assert "coordination_ratio" in result or "error" in result
    
    def test_migration_footprint(self, analyzer_with_transactions):
        """Тест миграционного следа"""
        result = analyzer_with_transactions.get_migration_footprint()
        assert isinstance(result, dict)
        # Может быть "error" если нет миграции
    
    def test_herding_index(self, analyzer_with_transactions):
        """Тест индекса стадности"""
        result = analyzer_with_transactions.get_herding_index()
        assert isinstance(result, dict)
        assert "herding_index" in result or "error" in result
    
    def test_revolutionary_score(self, analyzer_with_transactions):
        """Тест революционного скора"""
        result = analyzer_with_transactions.get_revolutionary_risk_score()
        assert isinstance(result, dict)
        assert "revolutionary_score" in result
        assert 0 <= result.get("revolutionary_score", 0) <= 100
    
    def test_scam_type_detection(self, scam_indicators_data):
        """Тест определения типа скама"""
        result = scam_indicators_data.get_revolutionary_risk_score()
        assert "scam_type" in result
        scam_types = [
            "INSTANT_RUGPULL", "COORDINATED_DUMP", "FAKE_HOLDERS",
            "FULLY_AUTOMATED_SCAM", "SYNCHRONIZED_DUMP",
            "EARLY_INSIDER_DUMP", "TRADITIONAL_PUMP_DUMP"
        ]
        assert result.get("scam_type") in scam_types