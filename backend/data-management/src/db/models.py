# data-management/src/db/models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TokenStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


@dataclass
class TokenInfo:
    mint: str
    symbol: Optional[str] = None
    name: Optional[str] = None
    decimals: int = 0
    supply: int = 0
    supply_formatted: float = 0.0


@dataclass
class TokenMetrics:
    mint: str
    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    volume_24h: float = 0.0
    volume_1h: float = 0.0
    volume_5m: float = 0.0
    holders_count: int = 0
    transactions_24h: int = 0
    price_usd: float = 0.0
    price_change_24h: float = 0.0
    price_change_1h: float = 0.0
    liquidity_usd: float = 0.0
    market_cap_usd: float = 0.0
    last_update: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ChartPoint:
    timestamp: datetime
    price: float
    volume: float
    transactions: int
    holders: int


@dataclass
class TokenAnalysis:
    mint: str
    token_info: TokenInfo
    metrics: TokenMetrics
    signatures_count: int
    transactions_count: int
    success_rate: float
    collection_time: float
    chart_data: List[ChartPoint] = field(default_factory=list)
    top_holders: List[Dict[str, Any]] = field(default_factory=list)
    anomalies: List[str] = field(default_factory=list)


@dataclass
class SystemMetrics:
    total_tokens_analyzed: int = 0
    total_transactions_processed: int = 0
    active_collectors: int = 0
    redis_memory_usage_mb: float = 0.0
    last_collection_time: Optional[datetime] = None
    uptime_seconds: float = 0.0


@dataclass
class QueueTask:
    task_id: str
    task_type: str
    token_mint: str
    payload: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0
    max_retries: int = 3