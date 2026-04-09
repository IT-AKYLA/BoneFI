import pytest
from datetime import datetime
from src.db.models import (
    RiskLevel, TokenStatus, TokenInfo, TokenMetrics,
    ChartPoint, TokenAnalysis, SystemMetrics, QueueTask
)


class TestModels:
    
    def test_risk_level_enum(self):
        """Тест уровней риска"""
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"
    
    def test_token_status_enum(self):
        """Тест статусов токена"""
        assert TokenStatus.ACTIVE == "active"
        assert TokenStatus.SUSPENDED == "suspended"
        assert TokenStatus.CLOSED == "closed"
    
    def test_token_info_creation(self):
        """Тест создания TokenInfo"""
        info = TokenInfo(
            mint="TestMint",
            symbol="TEST",
            name="Test Token",
            decimals=6,
            supply=1000000000,
            supply_formatted=1000.0
        )
        assert info.mint == "TestMint"
        assert info.symbol == "TEST"
        assert info.decimals == 6
    
    def test_token_metrics_creation(self):
        """Тест создания TokenMetrics"""
        metrics = TokenMetrics(
            mint="TestMint",
            risk_score=85.5,
            risk_level=RiskLevel.HIGH,
            volume_24h=1000000.0,
            holders_count=5000,
            price_usd=0.05
        )
        assert metrics.mint == "TestMint"
        assert metrics.risk_score == 85.5
        assert metrics.risk_level == RiskLevel.HIGH
        assert metrics.holders_count == 5000
    
    def test_chart_point_creation(self):
        """Тест создания ChartPoint"""
        now = datetime.now()
        point = ChartPoint(
            timestamp=now,
            price=0.05,
            volume=10000.0,
            transactions=100,
            holders=500
        )
        assert point.timestamp == now
        assert point.price == 0.05
        assert point.volume == 10000.0
        assert point.transactions == 100
    
    def test_token_analysis_creation(self):
        """Тест создания TokenAnalysis"""
        info = TokenInfo(mint="TestMint", decimals=6)
        metrics = TokenMetrics(mint="TestMint")
        
        analysis = TokenAnalysis(
            mint="TestMint",
            token_info=info,
            metrics=metrics,
            signatures_count=1000,
            transactions_count=800,
            success_rate=80.0,
            collection_time=5.5
        )
        assert analysis.mint == "TestMint"
        assert analysis.signatures_count == 1000
        assert analysis.success_rate == 80.0
    
    def test_system_metrics_creation(self):
        """Тест создания SystemMetrics"""
        metrics = SystemMetrics(
            total_tokens_analyzed=150,
            total_transactions_processed=100000,
            active_collectors=3,
            redis_memory_usage_mb=256.5
        )
        assert metrics.total_tokens_analyzed == 150
        assert metrics.active_collectors == 3
    
    def test_queue_task_creation(self):
        """Тест создания QueueTask"""
        task = QueueTask(
            task_id="task_123",
            task_type="collect",
            token_mint="TestMint",
            payload={"force": True}
        )
        assert task.task_id == "task_123"
        assert task.task_type == "collect"
        assert task.token_mint == "TestMint"
        assert task.retry_count == 0
        assert task.max_retries == 3
    
    def test_queue_task_defaults(self):
        """Тест значений по умолчанию QueueTask"""
        task = QueueTask(
            task_id="task_456",
            task_type="analyze",
            token_mint="AnotherMint",
            payload={}
        )
        assert task.retry_count == 0
        assert task.max_retries == 3
        assert task.created_at is not None