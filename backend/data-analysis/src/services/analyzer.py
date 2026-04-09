import math
import asyncio 
import gzip
import hashlib
import json
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple, Any, Callable
from collections import defaultdict
from functools import wraps
from scipy import stats
from scipy.spatial.distance import jensenshannon
import warnings
warnings.filterwarnings('ignore')

class TokenAnalyzer:
    def __init__(self, data: Dict, use_cache: bool = True, quick_mode: bool = False):
        self.raw_data = data
        self.token_mint = data.get("token_mint", "")
        self.use_cache = use_cache
        self._redis = None
        self._cache_key = None
        self._method_cache = {}
        self._quick_mode = quick_mode
        self._cache_loaded = False
        self._initialized = False
        self.token_info = data.get("token_info", {})
        self.decimals = self.token_info.get("decimals", 6)
        self.total_supply = self.token_info.get("supply", 0)
        self.total_supply_formatted = self.total_supply / (10 ** self.decimals) if self.total_supply else 0
        raw_transactions = data.get("transactions", [])
        self.transactions = []
        
        for item in raw_transactions:
            if isinstance(item, dict) and "result" in item:
                self.transactions.append(item["result"])
            else:
                self.transactions.append(item)
        if self._quick_mode and len(self.transactions) > 2000:
            self.transactions = self.transactions[:2000]
            
        self.current_holders: Dict[str, int] = {}
        self.historical_holders: Dict[str, int] = {}
        self.transferred_holders: Dict[str, Dict] = {}
        self.address_activity: Dict[str, int] = defaultdict(int)
        self.first_seen: Dict[str, float] = {}
        self.tx_timestamps: List[float] = []
        self.buy_volume: Dict[str, int] = defaultdict(int)
        self.sell_volume: Dict[str, int] = defaultdict(int)
        self.tx_prices: List[Dict] = []
        self.migration_time: Optional[float] = None
        
        # Новые поля для революционных метрик
        self._revolutionary_metrics_cache = {}
        self._holder_clusters_cache = None
        self._temporal_entropy_cache = None
        
        if use_cache:
            try:
                import redis
                import os
                REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
                self._redis = redis.from_url(REDIS_URL)
                self._cache_key = f"analyzer:{self.token_mint}:v2"
                cached = self._redis.get(self._cache_key)
                if cached:
                    cached_data = json.loads(cached)
                    self.current_holders = cached_data.get('current_holders', {})
                    self.historical_holders = cached_data.get('historical_holders', {})
                    self.address_activity = defaultdict(int, cached_data.get('address_activity', {}))
                    self.first_seen = cached_data.get('first_seen', {})
                    self.tx_timestamps = cached_data.get('tx_timestamps', [])
                    self.buy_volume = defaultdict(int, cached_data.get('buy_volume', {}))
                    self.sell_volume = defaultdict(int, cached_data.get('sell_volume', {}))
                    self.migration_time = cached_data.get('migration_time')
                    self._method_cache = cached_data.get('_method_cache', {})
                    self._revolutionary_metrics_cache = cached_data.get('_revolutionary_metrics_cache', {})
                    self._cache_loaded = True
                    self._initialized = True
                    return
            except Exception:
                pass
    
    def _to_native(self, obj):
        """Конвертирует numpy типы в стандартные Python типы"""
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        if hasattr(obj, 'item') and isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        if isinstance(obj, dict):
            return {k: self._to_native(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._to_native(i) for i in obj]
        return obj 
        
    def _ensure_initialized(self):
        """Ленивая инициализация - парсим данные только когда реально нужно"""
        if self._initialized:
            return
        
        if self._cache_loaded:
            self._initialized = True
            return
        
        if self._redis and self._cache_key:
            try:
                partial_cache = self._redis.get(f"{self._cache_key}:partial")
                if partial_cache:
                    partial_data = json.loads(partial_cache)
                    self.current_holders = partial_data.get('current_holders', {})
                    self.historical_holders = partial_data.get('historical_holders', {})
                    self.address_activity = defaultdict(int, partial_data.get('address_activity', {}))
                    self.first_seen = partial_data.get('first_seen', {})
                    self.tx_timestamps = partial_data.get('tx_timestamps', [])
                    self.migration_time = partial_data.get('migration_time')
                    self._revolutionary_metrics_cache = partial_data.get('_revolutionary_metrics_cache', {})
                    self._initialized = True
                    return
            except Exception:
                pass
        
        print(f"🔄 Performing full parsing for {self.token_mint}...")
        self._extract_all_data()
        self._find_migration_time()
        self._identify_transferred_holders()
        self._initialized = True
        
        if self._redis and self._cache_key:
            try:
                partial_data = {
                    'current_holders': self.current_holders,
                    'historical_holders': self.historical_holders,
                    'address_activity': dict(self.address_activity),
                    'first_seen': self.first_seen,
                    'tx_timestamps': self.tx_timestamps,
                    'migration_time': self.migration_time,
                    '_revolutionary_metrics_cache': self._revolutionary_metrics_cache
                }
                self._redis.setex(f"{self._cache_key}:partial", 300, json.dumps(partial_data, default=str))
            except Exception:
                pass
    
    def _cached_method(ttl: int = 3600):
            def decorator(func: Callable):
                @wraps(func)
                def wrapper(self, *args, **kwargs):
                    self._ensure_initialized()
                    cache_key = f"{func.__name__}:{hashlib.md5(str(args).encode() + str(kwargs).encode()).hexdigest()}"
                    if cache_key in self._method_cache:
                        return self._method_cache[cache_key]
                    result = func(self, *args, **kwargs)
                    result = self._to_native(result)
                    self._method_cache[cache_key] = result
                    if self._redis and hasattr(self, '_cache_key'):
                        try:
                            full_cache_key = f"{self._cache_key}:{func.__name__}"
                            self._redis.setex(full_cache_key, ttl, json.dumps(result, default=str))
                        except Exception:
                            pass
                    return result
                return wrapper
            return decorator
    
    def _extract_all_data(self):
        pool_addresses = self._identify_pools()
        
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp:
                self.tx_timestamps.append(timestamp)
            
            meta = tx.get("meta", {})
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]
            has_pool = any(addr in pool_addresses for addr in account_keys)
            
            if has_pool:
                total_change = 0
                changed_addresses = set()
                
                for bal in meta.get("preTokenBalances", []):
                    if bal.get("mint") == self.token_mint:
                        owner = bal.get("owner", "")
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        if owner and owner not in pool_addresses:
                            total_change -= amount
                            changed_addresses.add(owner)
                
                for bal in meta.get("postTokenBalances", []):
                    if bal.get("mint") == self.token_mint:
                        owner = bal.get("owner", "")
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        if owner and owner not in pool_addresses:
                            total_change += amount
                            changed_addresses.add(owner)
                
                if total_change > 0:
                    for owner in changed_addresses:
                        self.buy_volume[owner] += abs(total_change)
                elif total_change < 0:
                    for owner in changed_addresses:
                        self.sell_volume[owner] += abs(total_change)
            
            for bal in meta.get("preTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                    if owner and amount > 0:
                        if owner not in self.historical_holders or amount > self.historical_holders[owner]:
                            self.historical_holders[owner] = amount
            
            for bal in meta.get("postTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                    if owner and amount > 0:
                        if owner not in self.historical_holders or amount > self.historical_holders[owner]:
                            self.historical_holders[owner] = amount
                        if owner not in self.current_holders or amount > self.current_holders[owner]:
                            self.current_holders[owner] = amount
            
            for acc in account_keys:
                if len(acc) > 30:
                    self.address_activity[acc] += 1
                    if acc not in self.first_seen or (timestamp and timestamp < self.first_seen[acc]):
                        self.first_seen[acc] = timestamp
    
    @_cached_method(ttl=600)
    def get_temporal_entropy(self) -> Dict:

        if len(self.tx_timestamps) < 10:
            return {"error": "Insufficient data", "entropy_score": 0.5, "confidence": 0.3}
        
        # Сортируем временные метки
        sorted_timestamps = sorted(self.tx_timestamps)
        
        # Вычисляем интервалы между транзакциями
        intervals = np.diff(sorted_timestamps)
        
        if len(intervals) < 5:
            return {"error": "Insufficient intervals", "entropy_score": 0.5, "confidence": 0.3}
        
        # Нормализуем интервалы
        intervals_normalized = intervals / (intervals.max() + 1e-10)
        
        # Вычисляем энтропию Шеннона
        hist, bin_edges = np.histogram(intervals_normalized, bins=20, density=True)
        hist = hist / (hist.sum() + 1e-10)
        hist = hist[hist > 0]
        entropy = -np.sum(hist * np.log2(hist)) / np.log2(20)  # Нормализованная энтропия 0-1
        
        # Дополнительные метрики
        cv = np.std(intervals) / (np.mean(intervals) + 1e-10)  # Коэффициент вариации
        uniformity = 1.0 - min(1.0, cv / 5.0)  # Равномерность 0-1
        
        # Финальный скор
        final_score = entropy * 0.6 + uniformity * 0.4
        
        # Определение паттерна
        if final_score < 0.15:
            pattern = "FULLY_AUTOMATED_SCAM"
            scam_confidence = 0.95
        elif final_score < 0.3:
            pattern = "HIGHLY_AUTOMATED"
            scam_confidence = 0.85
        elif final_score < 0.5:
            pattern = "MIXED_PATTERN"
            scam_confidence = 0.6
        elif final_score < 0.7:
            pattern = "NATURAL_PATTERN"
            scam_confidence = 0.3
        else:
            pattern = "HUMAN_PATTERN"
            scam_confidence = 0.1
        
        return {
            "entropy_score": round(final_score, 4),
            "raw_entropy": round(entropy, 4),
            "uniformity": round(uniformity, 4),
            "coefficient_variation": round(cv, 2),
            "pattern": pattern,
            "scam_confidence": scam_confidence,
            "is_suspicious": final_score < 0.3,
            "is_critical": final_score < 0.15
        }
    
    @_cached_method(ttl=600)
    def get_anti_fragmentation(self) -> Dict:
        if not self.current_holders:
            return {"error": "No holders", "artificial_inflation": 0, "scam_confidence": 0}
        
        total_holders = len(self.current_holders)
        
        # Группировка по первым 8 символам (высокая вероятность одного владельца)
        address_groups = defaultdict(list)
        for addr in self.current_holders.keys():
            prefix = addr[:8]
            address_groups[prefix].append(addr)
        
        # Поиск кластеров с одинаковым временем создания
        time_clusters = defaultdict(list)
        for addr, first_seen in self.first_seen.items():
            if first_seen:
                time_window = int(first_seen // 300)  # 5-минутные окна
                time_clusters[time_window].append(addr)
        
        # Расчет фрагментации
        suspicious_groups = 0
        artificial_count = 0
        
        for prefix, addrs in address_groups.items():
            if len(addrs) >= 3:
                # Проверяем, похожи ли их паттерны транзакций
                suspicious_groups += 1
                artificial_count += len(addrs) - 1  # Один реальный, остальные фейковые
        
        # Анализ временных кластеров
        for window, addrs in time_clusters.items():
            if len(addrs) >= 5:
                # Слишком много кошельков создано в одно время
                artificial_count += len(addrs) // 2
        
        # Реальное количество уникальных владельцев
        real_holders = max(1, total_holders - artificial_count)
        artificial_inflation = (artificial_count / total_holders * 100) if total_holders > 0 else 0
        
        # Оценка скама
        if artificial_inflation >= 70:
            scam_confidence = 0.95
            risk_level = "CRITICAL"
        elif artificial_inflation >= 50:
            scam_confidence = 0.85
            risk_level = "HIGH"
        elif artificial_inflation >= 30:
            scam_confidence = 0.7
            risk_level = "MEDIUM"
        elif artificial_inflation >= 10:
            scam_confidence = 0.5
            risk_level = "LOW"
        else:
            scam_confidence = 0.1
            risk_level = "MINIMAL"
        
        return {
            "total_holders_reported": total_holders,
            "estimated_real_holders": real_holders,
            "artificial_count": artificial_count,
            "artificial_inflation_percent": round(artificial_inflation, 1),
            "suspicious_clusters": suspicious_groups,
            "risk_level": risk_level,
            "scam_confidence": scam_confidence,
            "is_fragmented": artificial_inflation > 30
        }
    
    @_cached_method(ttl=600)
    def get_domino_effect(self) -> Dict:
        if len(self.transactions) < 100:
            return {"error": "Insufficient data", "coordination_detected": False}
        
        # Анализ продаж во времени
        sell_events = []
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue
            
            meta = tx.get("meta", {})
            for bal in meta.get("preTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                    if amount > 0:
                        sell_events.append((timestamp, amount))
        
        if len(sell_events) < 10:
            return {"error": "Insufficient sell events", "coordination_detected": False}
        
        sell_events.sort(key=lambda x: x[0])
        
        # Поиск кластеров продаж
        clusters = []
        current_cluster = []
        time_threshold = 15  
        
        for i, (ts, amount) in enumerate(sell_events):
            if not current_cluster:
                current_cluster.append((ts, amount))
            else:
                last_ts = current_cluster[-1][0]
                if ts - last_ts <= time_threshold:
                    current_cluster.append((ts, amount))
                else:
                    if len(current_cluster) >= 3:
                        clusters.append(current_cluster)
                    current_cluster = [(ts, amount)]
        
        if len(current_cluster) >= 3:
            clusters.append(current_cluster)
        
        # Расчет скоординированности
        coordinated_clusters = 0
        total_coordinated_volume = 0
        
        for cluster in clusters:
            cluster_volume = sum(amt for _, amt in cluster)
            if cluster_volume > 1_000_000:  # Значительный объем
                coordinated_clusters += 1
                total_coordinated_volume += cluster_volume
        
        total_sell_volume = sum(amt for _, amt in sell_events)
        coordination_ratio = total_coordinated_volume / (total_sell_volume + 1e-10)
        
        # Оценка
        if coordination_ratio > 0.5:
            scam_confidence = 0.95
            risk_level = "CRITICAL"
        elif coordination_ratio > 0.3:
            scam_confidence = 0.85
            risk_level = "HIGH"
        elif coordination_ratio > 0.15:
            scam_confidence = 0.7
            risk_level = "MEDIUM"
        elif coordination_ratio > 0.05:
            scam_confidence = 0.4
            risk_level = "LOW"
        else:
            scam_confidence = 0.1
            risk_level = "MINIMAL"
        
        return {
            "coordinated_clusters": coordinated_clusters,
            "coordination_ratio": round(coordination_ratio, 3),
            "total_coordinated_volume_millions": total_coordinated_volume / (10 ** self.decimals) / 1_000_000,
            "risk_level": risk_level,
            "scam_confidence": scam_confidence,
            "coordination_detected": coordination_ratio > 0.15
        }
    
    @_cached_method(ttl=600)
    def get_migration_footprint(self) -> Dict:
        """
        МЕТРИКА №4: Миграционный след
        Анализирует поведение при миграции
        """
        if not self.migration_time:
            return {"error": "No migration detected"}
        
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0
        migration_ts = self.migration_time
        
        # Анализ ранних холдеров
        early_holders = {}
        for addr, first_seen in self.first_seen.items():
            if first_seen and first_seen < migration_ts:
                early_holders[addr] = {
                    "first_seen": first_seen,
                    "balance": self.current_holders.get(addr, 0)
                }
        
        # Определяем, кто продал после миграции
        sold_after_migration = set()
        for addr in early_holders:
            current_balance = self.current_holders.get(addr, 0)
            if current_balance == 0:
                sold_after_migration.add(addr)
        
        total_early = len(early_holders)
        sold_count = len(sold_after_migration)
        sold_ratio = sold_count / total_early if total_early > 0 else 0
        
        # Анализ времени продаж
        early_sells = []
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp and timestamp > migration_ts:
                meta = tx.get("meta", {})
                for bal in meta.get("preTokenBalances", []):
                    if bal.get("mint") == self.token_mint:
                        owner = bal.get("owner", "")
                        if owner in early_holders:
                            early_sells.append(timestamp - migration_ts)
        
        # Время первого дампа
        first_dump_time = min(early_sells) if early_sells else None
        dump_ratio_5min = sum(1 for t in early_sells if t < 300) / len(early_sells) if early_sells else 0
        dump_ratio_30min = sum(1 for t in early_sells if t < 1800) / len(early_sells) if early_sells else 0
        
        # Оценка риска
        if sold_ratio > 0.7 or dump_ratio_5min > 0.5:
            scam_confidence = 0.95
            risk_level = "CRITICAL"
            verdict = "MASSIVE_INSTANT_DUMP"
        elif sold_ratio > 0.5 or dump_ratio_30min > 0.5:
            scam_confidence = 0.85
            risk_level = "HIGH"
            verdict = "SIGNIFICANT_EARLY_DUMP"
        elif sold_ratio > 0.3:
            scam_confidence = 0.7
            risk_level = "MEDIUM"
            verdict = "MODERATE_DUMP"
        elif sold_ratio > 0.1:
            scam_confidence = 0.4
            risk_level = "LOW"
            verdict = "MINOR_DUMP"
        else:
            scam_confidence = 0.1
            risk_level = "MINIMAL"
            verdict = "HELD"
        
        return {
            "total_early_holders": total_early,
            "sold_after_migration": sold_count,
            "sold_ratio": round(sold_ratio, 3),
            "dump_ratio_5min": round(dump_ratio_5min, 3),
            "dump_ratio_30min": round(dump_ratio_30min, 3),
            "first_dump_seconds": int(first_dump_time) if first_dump_time else None,
            "risk_level": risk_level,
            "scam_confidence": scam_confidence,
            "verdict": verdict,
            "is_rugpull": sold_ratio > 0.5
        }
    
    @_cached_method(ttl=600)
    def get_herding_index(self) -> Dict:
        """
        МЕТРИКА №5: Индекс стадного чувства
        Обнаруживает синхронные действия (армии ботов)
        """
        if len(self.transactions) < 50:
            return {"error": "Insufficient data", "herding_index": 0}
        
        # Группируем транзакции по временным окнам (10 секунд)
        time_windows = defaultdict(list)
        
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue
            
            window = int(timestamp // 10)  # 10-секундные окна
            
            # Определяем тип транзакции
            meta = tx.get("meta", {})
            tx_type = "unknown"
            for bal in meta.get("postTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    tx_type = "buy"
                    break
            for bal in meta.get("preTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    tx_type = "sell"
                    break
            
            time_windows[window].append(tx_type)
        
        # Расчет индекса стадности
        window_scores = []
        for window, actions in time_windows.items():
            if len(actions) >= 5:
                buy_count = actions.count("buy")
                sell_count = actions.count("sell")
                majority_ratio = max(buy_count, sell_count) / len(actions)
                window_scores.append(majority_ratio)
        
        herding_index = np.mean(window_scores) if window_scores else 0
        
        # Оценка
        if herding_index > 0.8:
            scam_confidence = 0.95
            risk_level = "CRITICAL"
            verdict = "EXTREME_HERDING"
        elif herding_index > 0.65:
            scam_confidence = 0.85
            risk_level = "HIGH"
            verdict = "STRONG_HERDING"
        elif herding_index > 0.5:
            scam_confidence = 0.7
            risk_level = "MEDIUM"
            verdict = "MODERATE_HERDING"
        elif herding_index > 0.35:
            scam_confidence = 0.4
            risk_level = "LOW"
            verdict = "WEAK_HERDING"
        else:
            scam_confidence = 0.1
            risk_level = "MINIMAL"
            verdict = "INDEPENDENT_ACTIONS"
        
        # Детекция армии ботов
        bot_army_detected = herding_index > 0.65
        
        return {
            "herding_index": round(herding_index, 4),
            "synchronized_windows": len(window_scores),
            "risk_level": risk_level,
            "scam_confidence": scam_confidence,
            "verdict": verdict,
            "bot_army_detected": bot_army_detected
        }
    
    @_cached_method(ttl=600)
    def get_revolutionary_risk_score(self) -> Dict:
        # Получаем все метрики
        temporal = self.get_temporal_entropy()
        anti_frag = self.get_anti_fragmentation()
        domino = self.get_domino_effect()
        migration = self.get_migration_footprint()
        herding = self.get_herding_index()
        
        # Безопасное извлечение значений
        temporal_score = 1.0 - temporal.get("entropy_score", 0.5) if "error" not in temporal else 0.5
        anti_frag_score = anti_frag.get("artificial_inflation_percent", 0) / 100 if "error" not in anti_frag else 0.5
        domino_score = domino.get("coordination_ratio", 0) if "error" not in domino else 0
        migration_score = migration.get("sold_ratio", 0) if "error" not in migration else 0
        herding_score = herding.get("herding_index", 0) if "error" not in herding else 0
        
        # Взвешенная сумма (веса подобраны эмпирически)
        revolutionary_score = (
            temporal_score * 3.0 +      # Энтропия - самый важный
            anti_frag_score * 2.5 +     # Анти-фрагментация
            domino_score * 2.5 +        # Эффект домино
            migration_score * 2.0 +     # Миграционный след
            herding_score * 2.0         # Стадное чувство
        ) / 12.0 * 100  # Нормализация в 0-100
        
        revolutionary_score = min(100, max(0, revolutionary_score))
        
        # Определение типа скама
        scam_type = self._identify_scam_type(temporal, anti_frag, domino, migration, herding)
        
        # Уровень риска
        if revolutionary_score >= 70:
            risk_level = "CRITICAL"
            recommendation = "STRONG AVOID - Multiple scam indicators detected"
        elif revolutionary_score >= 50:
            risk_level = "HIGH"
            recommendation = "AVOID - Strong scam probability"
        elif revolutionary_score >= 30:
            risk_level = "MEDIUM"
            recommendation = "CAUTION - Suspicious patterns detected"
        elif revolutionary_score >= 15:
            risk_level = "LOW"
            recommendation = "POTENTIAL - Minor suspicious activity"
        else:
            risk_level = "MINIMAL"
            recommendation = "LIKELY_LEGIT - No scam patterns detected"
        
        return {
            "revolutionary_score": round(revolutionary_score, 2),
            "risk_level": risk_level,
            "recommendation": recommendation,
            "scam_type": scam_type,
            "confidence": round(85 + revolutionary_score * 0.15, 1),  # 85-100%
            "metrics": {
                "temporal_entropy": temporal if "error" not in temporal else None,
                "anti_fragmentation": anti_frag if "error" not in anti_frag else None,
                "domino_effect": domino if "error" not in domino else None,
                "migration_footprint": migration if "error" not in migration else None,
                "herding_index": herding if "error" not in herding else None
            }
        }
    
    def _identify_scam_type(self, temporal: Dict, anti_frag: Dict, domino: Dict, migration: Dict, herding: Dict) -> str:
        """Определяет конкретный тип скама на основе метрик"""
        if "error" not in migration and migration.get("sold_ratio", 0) > 0.7:
            return "INSTANT_RUGPULL"
        elif "error" not in herding and herding.get("herding_index", 0) > 0.7:
            return "COORDINATED_DUMP"
        elif "error" not in anti_frag and anti_frag.get("artificial_inflation_percent", 0) > 60:
            return "FAKE_HOLDERS"
        elif "error" not in temporal and temporal.get("entropy_score", 1) < 0.15:
            return "FULLY_AUTOMATED_SCAM"
        elif "error" not in domino and domino.get("coordination_ratio", 0) > 0.4:
            return "SYNCHRONIZED_DUMP"
        elif "error" not in migration and migration.get("dump_ratio_5min", 0) > 0.3:
            return "EARLY_INSIDER_DUMP"
        else:
            return "TRADITIONAL_PUMP_DUMP"
    
    def _identify_transferred_holders(self):
        for addr, historical_balance in self.historical_holders.items():
            current_balance = self.current_holders.get(addr, 0)
            if current_balance == 0 and historical_balance > 0:
                self.transferred_holders[addr] = {
                    "max_balance": historical_balance,
                    "status": "SOLD"
                }
            elif current_balance < historical_balance * 0.5:
                self.transferred_holders[addr] = {
                    "max_balance": historical_balance,
                    "status": "PARTIAL_TRANSFER"
                }
    
    def _identify_pools(self) -> Set[str]:
        pools = set()
        total_balance = sum(self.current_holders.values()) if self.current_holders else 0
        
        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            tx_count = self.address_activity.get(addr, 0)
            if share >= 3 and tx_count > 50:
                pools.add(addr)
        
        pump_program = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        raydium_program = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
        
        for tx in self.transactions:
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]
            if pump_program in account_keys or raydium_program in account_keys:
                for acc in account_keys:
                    if len(acc) > 30:
                        pools.add(acc)
        
        return pools

    def _find_migration_time(self):
        pump_program = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
        raydium_program = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
        
        if not self.tx_timestamps:
            self.migration_time = None
            return
        
        creation_time = min(self.tx_timestamps)
        sorted_txs = sorted(self.transactions, key=lambda tx: tx.get("blockTime", 0))
        
        for tx in sorted_txs:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0 or timestamp == creation_time:
                continue
            
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]
            
            if pump_program in account_keys or raydium_program in account_keys:
                self.migration_time = timestamp
                return
        
        self.migration_time = None
    
    def _save_to_history_sync(self, analysis_result: Dict):
        try:
            if not self._redis:
                import redis
                import os
                REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
                self._redis = redis.from_url(REDIS_URL)
            
            clean_result = self._to_native(analysis_result)
            
            key = f"history:{self.token_mint}"
            json_str = json.dumps(clean_result, default=str)
            compressed = gzip.compress(json_str.encode('utf-8'))
            self._redis.setex(key, 604800, compressed)
            
            quick_key = f"quick:{self.token_mint}"
            quick_data = {
                'risk_score': clean_result.get('risk_assessment', {}).get('score', 0),
                'revolutionary_score': clean_result.get('revolutionary_metrics', {}).get('revolutionary_score', 0),
                'summary': clean_result.get('summary', {}),
                'analyzed_at': datetime.now().isoformat()
            }
            self._redis.setex(quick_key, 3600, json.dumps(quick_data, default=str))
            
            today = datetime.now().strftime("%Y-%m-%d")
            risk_score = clean_result.get("risk_assessment", {}).get("score", 0)
            self._redis.zadd(f"analytics:daily:{today}", {self.token_mint: risk_score})
            self._redis.expire(f"analytics:daily:{today}", 86400 * 30)
            
            cache_data = {
                'current_holders': self._to_native(self.current_holders),
                'historical_holders': self._to_native(self.historical_holders),
                'address_activity': self._to_native(dict(self.address_activity)),
                'first_seen': self._to_native(self.first_seen),
                'tx_timestamps': self._to_native(self.tx_timestamps),
                'buy_volume': self._to_native(dict(self.buy_volume)),
                'sell_volume': self._to_native(dict(self.sell_volume)),
                'migration_time': self.migration_time,
                '_method_cache': self._to_native(self._method_cache),
                '_revolutionary_metrics_cache': self._to_native(self._revolutionary_metrics_cache)
            }
            self._redis.setex(f"analyzer:{self.token_mint}:v2", 600, json.dumps(cache_data, default=str))
            
        except Exception as e:
            print(f"Error saving to history: {e}")

    def _is_market_maker(self, addr: str) -> bool:
        balance = self.current_holders.get(addr, 0)
        total_balance = sum(self.current_holders.values()) if self.current_holders else 0
        share = (balance / total_balance * 100) if total_balance > 0 else 0
        tx_count = self.address_activity.get(addr, 0)
        first_seen = self.first_seen.get(addr, 0)
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0
        minutes_after_start = (first_seen - creation_time) / 60 if first_seen and creation_time else 999

        if minutes_after_start < 5:
            return False
        if self._is_rapid_seller(addr, creation_time):
            return False
        if self._is_in_cluster(addr):
            return False
        if share < 0.5 and tx_count > 30:
            return True
        return False

    def _is_in_cluster_metric(self) -> float:
        """Возвращает процент кошельков, находящихся в кластерах"""
        if not self.current_holders:
            return 0.0
        
        total_holders = len(self.current_holders)
        in_cluster = 0
        
        for addr in self.current_holders:
            if self._is_in_cluster(addr):
                in_cluster += 1
        
        return in_cluster / total_holders if total_holders > 0 else 0.0
    
    
    def _is_coordinated_metric(self) -> float:
        """Возвращает процент координации (0-1)"""
        if not self.current_holders:
            return 0.0
        
        coordinated_count = 0
        for addr in self.current_holders:
            if self._is_coordinated(addr):
                coordinated_count += 1
        
        return coordinated_count / len(self.current_holders) if self.current_holders else 0.0    

    def get_market_maker_share(self) -> float:
        if not self.current_holders:
            return 0.0
        total_balance = sum(self.current_holders.values())
        mm_balance = 0
        for addr, balance in self.current_holders.items():
            if self._is_market_maker(addr):
                mm_balance += balance
        return (mm_balance / total_balance * 100) if total_balance > 0 else 0.0

    @_cached_method(ttl=600)
    def get_malicious_supply_index(self) -> Dict:
        if not self.current_holders:
            return {"error": "No holders"}

        total_balance = sum(self.current_holders.values())
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0

        malicious_supply = 0
        malicious_wallets = []

        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            tx_count = self.address_activity.get(addr, 0)
            first_seen = self.first_seen.get(addr, 0)
            minutes_after_start = (first_seen - creation_time) / 60 if first_seen and creation_time else 999

            is_pool = self.is_liquidity_pool(addr, share, tx_count)
            if is_pool:
                continue
            
            if self._is_market_maker(addr):
                continue
            
            is_malicious = False

            if minutes_after_start < 5 and share > 0.08:
                is_malicious = True
            elif self._is_rapid_seller(addr, creation_time):
                is_malicious = True
            elif self._is_in_cluster(addr):
                is_malicious = True
            elif share > 0.3 and tx_count < 20 and minutes_after_start < 30:
                is_malicious = True
            elif self._is_coordinated(addr):
                is_malicious = True

            if is_malicious:
                malicious_supply += balance
                malicious_wallets.append(addr)

        malicious_percent = (malicious_supply / total_balance * 100) if total_balance > 0 else 0

        if malicious_percent >= 30:
            risk_level = "CRITICAL"
            recommendation = "STRONG AVOID - более 30% под вредными ботами"
        elif malicious_percent >= 15:
            risk_level = "HIGH"
            recommendation = "AVOID - значительная доля вредных ботов"
        elif malicious_percent >= 5:
            risk_level = "MEDIUM"
            recommendation = "CAUTION - присутствуют вредные боты"
        else:
            risk_level = "LOW"
            recommendation = "POTENTIAL - вредные боты в норме"

        return {
            "malicious_supply_percent": round(malicious_percent, 1),
            "risk_level": risk_level,
            "recommendation": recommendation,
            "malicious_wallets_count": len(malicious_wallets)
        }
    
    def is_liquidity_pool(self, addr: str, share: float, tx_count: int) -> bool:
        if share >= 3 and tx_count > 10:
            return True
        if tx_count > 1000:
            return True
        return False
    
    def is_bot(self, share: float) -> bool:
        return share < 0.03
    
    @_cached_method(ttl=300)
    def get_top_holders_full(self, limit: int = 15) -> List[Dict]:
        if not self.current_holders:
            return []

        total_balance = sum(self.current_holders.values())
        holders = []

        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            tx_count = self.address_activity.get(addr, 0)

            is_pool = self.is_liquidity_pool(addr, share, tx_count)
            is_whale = share > 5 and not is_pool
            is_large = share > 1 and not is_pool and not is_whale

            if is_pool:
                holder_type = "POOL"
            elif is_whale:
                holder_type = "WHALE"
            elif is_large:
                holder_type = "LARGE"
            else:
                holder_type = "holder"

            holders.append({
                "address": self._get_address_short(addr),
                "balance_millions": balance / (10 ** self.decimals) / 1_000_000,
                "share_percentage": round(share, 2),
                "tx_count": tx_count,
                "type": holder_type,
                "is_pool": is_pool
            })

        holders.sort(key=lambda x: x["share_percentage"], reverse=True)
        return holders[:limit]
    
    def _format_address(self, address: str) -> str:
        if len(address) < 12:
            return address
        return f"{address[:4]}...{address[-4:]}"
    
    def _get_address_short(self, address: str) -> str:
        if len(address) < 8:
            return address
        return address[:4]
    
    def _is_rapid_seller(self, addr: str, creation_time: float) -> bool:
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0 or timestamp > creation_time + 300:
                continue
            
            tx_meta = tx.get("meta", {})
            for bal in tx_meta.get("preTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    if owner == addr:
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        if amount > 0:
                            return True
        return False

    def _is_in_cluster(self, addr: str) -> bool:
        first_seen = self.first_seen.get(addr, 0)
        if not first_seen:
            return False

        balance = self.current_holders.get(addr, 0)
        total_balance = sum(self.current_holders.values()) if self.current_holders else 0
        share = (balance / total_balance * 100) if total_balance > 0 else 0
        tx_count = self.address_activity.get(addr, 0)

        if self.is_liquidity_pool(addr, share, tx_count):
            return False

        same_time_count = 0
        for other_addr, other_first in self.first_seen.items():
            if other_addr != addr and abs(other_first - first_seen) < 60:
                other_balance = self.current_holders.get(other_addr, 0)
                other_share = (other_balance / total_balance * 100) if total_balance > 0 else 0
                other_tx_count = self.address_activity.get(other_addr, 0)
                if self.is_liquidity_pool(other_addr, other_share, other_tx_count):
                    continue
                same_time_count += 1
                if same_time_count >= 3:
                    return True
        return False

    def _is_coordinated(self, addr: str) -> bool:
        balance = self.current_holders.get(addr, 0)
        total_balance = sum(self.current_holders.values()) if self.current_holders else 0
        share = (balance / total_balance * 100) if total_balance > 0 else 0
        tx_count = self.address_activity.get(addr, 0)
        
        if self.is_liquidity_pool(addr, share, tx_count):
            return False
        
        tx_times = []
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue
            
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]
    
            if addr in account_keys:
                tx_times.append(timestamp)
    
        if len(tx_times) < 3:
            return False
    
        tx_times.sort()
        for i in range(len(tx_times) - 2):
            if tx_times[i+2] - tx_times[i] < 10:
                return True
    
        return False
    
    def _did_sell_quickly(self, addr: str, buy_time: float) -> bool:
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0 or timestamp < buy_time or timestamp > buy_time + 300:
                continue
            
            tx_meta = tx.get("meta", {})
            for bal in tx_meta.get("preTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    if owner == addr:
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        if amount > 0:
                            return True
        return False
    
    def get_migration_speed_analysis(self) -> Dict:
        if not self.tx_timestamps:
            return {"error": "No data"}

        creation_time = min(self.tx_timestamps)

        if not self.migration_time:
            return {
                "creation_time": datetime.fromtimestamp(creation_time).strftime("%Y-%m-%d %H:%M:%S"),
                "migration_time": "Not migrated",
                "seconds_to_migrate": None,
                "risk_score": 0,
                "verdict": "NOT_MIGRATED"
            }

        migration_time = self.migration_time
        seconds_to_migrate = migration_time - creation_time

        risk_verdict = [
            (60, 40, "INSTANT_MIGRATION"),
            (300, 25, "VERY_FAST_MIGRATION"),
            (3600, 10, "FAST_MIGRATION"),
            (float('inf'), 0, "NORMAL_MIGRATION_TIMEFRAME")
        ]

        risk, verdict = next((r, v) for limit, r, v in risk_verdict if seconds_to_migrate < limit)

        return {
            "creation_time": datetime.fromtimestamp(creation_time).strftime("%Y-%m-%d %H:%M:%S"),
            "migration_time": datetime.fromtimestamp(migration_time).strftime("%Y-%m-%d %H:%M:%S"),
            "seconds_to_migrate": int(seconds_to_migrate),
            "risk_score": risk,
            "verdict": verdict
        }
    
    def get_historical_holders(self) -> List[Dict]:
        result = []

        for addr, data in self.transferred_holders.items():
            max_balance = data["max_balance"]
            status = data["status"]

            current_balance = self.current_holders.get(addr, 0)
            tx_count = self.address_activity.get(addr, 0)
            total_balance = sum(self.current_holders.values())
            max_share = (max_balance / total_balance * 100) if total_balance > 0 else 0

            result.append({
                "address": self._get_address_short(addr),
                "max_balance_millions": max_balance / (10 ** self.decimals) / 1_000_000,
                "current_balance_millions": current_balance / (10 ** self.decimals) / 1_000_000,
                "max_share": round(max_share, 2),
                "tx_count": tx_count,
                "status": status
            })

        result.sort(key=lambda x: x["max_balance_millions"], reverse=True)
        return result[:20] 
    
    def get_pre_migration_top_holders(self, limit: int = 15, min_share: float = 0.03) -> List[Dict]:
        if not self.migration_time:
            return []

        migration_ts = self.migration_time
        if isinstance(migration_ts, datetime):
            migration_ts = migration_ts.timestamp()

        pre_holders = {}
        for addr, balance in self.current_holders.items():
            first_seen = self.first_seen.get(addr, 0)
            if first_seen < migration_ts:
                pre_holders[addr] = balance

        total_balance = sum(pre_holders.values())
        holders = []

        for addr, balance in pre_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            if share < min_share:
                continue
            
            tx_count = self.address_activity.get(addr, 0)
            is_pool = self.is_liquidity_pool(addr, share, tx_count)

            if is_pool:
                holder_type = "POOL"
            elif share > 5:
                holder_type = "WHALE"
            elif share > 1:
                holder_type = "LARGE"
            else:
                holder_type = "holder"

            holders.append({
                "address": self._get_address_short(addr),
                "balance_millions": balance / (10 ** self.decimals) / 1_000_000,
                "share_percentage": round(share, 2),
                "tx_count": tx_count,
                "retained": addr in self.current_holders,
                "is_pool": is_pool,
                "type": holder_type
            })

        holders.sort(key=lambda x: x["share_percentage"], reverse=True)
        return holders[:limit]
    
    def get_whale_accumulation_rate(self, hours: int = 6) -> Dict:
        if not self.migration_time:
            return {"error": "No migration time"}
        
        migration_ts = self.migration_time
        if isinstance(migration_ts, datetime):
            migration_ts = migration_ts.timestamp()
        
        post_txs = [tx for tx in self.transactions if tx.get("blockTime", 0) >= migration_ts]
        
        if not post_txs:
            return {"rate": 0, "trend": "NO_DATA"}
        
        now = max(tx.get("blockTime", 0) for tx in post_txs)
        intervals = []
        
        for i in range(4):
            start = now - (i + 1) * hours * 3600
            end = now - i * hours * 3600
            
            holders_at_start = {}
            holders_at_end = {}
            
            for tx in post_txs:
                ts = tx.get("blockTime", 0)
                if start <= ts < end:
                    for bal in tx.get("meta", {}).get("postTokenBalances", []):
                        if bal.get("mint") == self.token_mint:
                            owner = bal.get("owner", "")
                            amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                            if amount > 0:
                                holders_at_end[owner] = amount
                elif end <= ts < now:
                    for bal in tx.get("meta", {}).get("postTokenBalances", []):
                        if bal.get("mint") == self.token_mint:
                            owner = bal.get("owner", "")
                            amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                            if amount > 0:
                                holders_at_start[owner] = amount
            
            top_10_start = sorted(holders_at_start.values(), reverse=True)[:10] if holders_at_start else []
            top_10_end = sorted(holders_at_end.values(), reverse=True)[:10] if holders_at_end else []
            
            whale_share_start = sum(top_10_start) / self.total_supply * 100 if self.total_supply else 0
            whale_share_end = sum(top_10_end) / self.total_supply * 100 if self.total_supply else 0
            
            intervals.append({
                "period": f"{i+1}",
                "whale_share_start": round(whale_share_start, 1),
                "whale_share_end": round(whale_share_end, 1),
                "change": round(whale_share_end - whale_share_start, 1)
            })
        
        latest_change = intervals[0]["change"] if intervals else 0
        
        if latest_change > 5:
            trend = "ACCUMULATING"
            risk = 0
        elif latest_change < -5:
            trend = "DUMPING"
            risk = 20
        else:
            trend = "STABLE"
            risk = 0
        
        return {
            "rate_percent": latest_change,
            "trend": trend,
            "risk_score": risk,
            "intervals": intervals
        }
    
    def get_sell_pressure_index(self) -> Dict:
        total_buy = sum(self.buy_volume.values())
        total_sell = sum(self.sell_volume.values())
        
        if total_buy == 0:
            ratio = 0
        else:
            ratio = total_sell / total_buy
        
        if ratio > 1.5:
            pressure = "HIGH"
            risk = 25
        elif ratio > 1.2:
            pressure = "MODERATE"
            risk = 15
        elif ratio > 1.0:
            pressure = "SLIGHT"
            risk = 5
        else:
            pressure = "LOW"
            risk = 0
        
        return {
            "buy_volume": round(total_buy / (10 ** self.decimals), 2),
            "sell_volume": round(total_sell / (10 ** self.decimals), 2),
            "ratio": round(ratio, 2),
            "pressure": pressure,
            "risk_score": risk
        }
        
    def detect_robotic_patterns(self) -> Dict:
        if not self.transactions:
            return {"error": "No transactions"}

        pool_set = set(self._identify_pools())
        total_supply = self.total_supply

        wallet_txs = defaultdict(list)

        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue
            
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]

            if not any(addr in pool_set for addr in account_keys):
                continue
            
            for bal in tx.get("meta", {}).get("postTokenBalances", []):
                if bal.get("mint") != self.token_mint:
                    continue
                
                owner = bal.get("owner", "")
                if not owner or owner in pool_set:
                    continue
                
                amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                if amount > 0:
                    amount_percent = (amount / total_supply * 100) if total_supply > 0 else 0
                    wallet_txs[owner].append({
                        "timestamp": timestamp,
                        "amount": amount,
                        "amount_percent": amount_percent
                    })

        def check_repeating_amounts(txs):
            amounts = [tx["amount"] for tx in txs]
            return len(set(amounts)) <= 3

        def check_perfect_intervals(txs):
            if len(txs) < 3:
                return False
            intervals = [txs[i+1]["timestamp"] - txs[i]["timestamp"] for i in range(len(txs)-1)]
            return len(set(intervals)) <= 2

        def check_continuous_activity(txs):
            if len(txs) < 50:
                return False

            for i in range(len(txs) - 50):
                time_window = txs[i+49]["timestamp"] - txs[i]["timestamp"]
                if time_window >= 600:
                    continue
                
                significant = sum(1 for tx in txs[i:i+50] if tx["amount_percent"] >= 0.05)
                if significant >= 5:
                    return True
            return False

        PATTERNS = [
            ("REPEATING_AMOUNTS", check_repeating_amounts, 
             lambda txs: f"Only {len(set(tx['amount'] for tx in txs))} unique amounts"),
            ("PERFECT_INTERVALS", check_perfect_intervals,
             lambda txs: f"Intervals: {list(set(txs[i+1]['timestamp'] - txs[i]['timestamp'] for i in range(len(txs)-1)))} seconds"),
            ("CONTINUOUS_ACTIVITY", check_continuous_activity,
             lambda txs: "50+ buys in 10 min with >0.05% supply each")
        ]

        robotic_wallets = []
        robotic_addresses = set()

        for addr, txs in wallet_txs.items():
            if len(txs) < 3:
                continue
            
            txs.sort(key=lambda x: x["timestamp"])

            for pattern_name, check_func, detail_func in PATTERNS:
                if check_func(txs):
                    robotic_wallets.append({
                        "address": self._get_address_short(addr),
                        "pattern": pattern_name,
                        "detail": detail_func(txs)
                    })
                    robotic_addresses.add(addr)
                    break
                
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0
        early_txs = [tx for tx in self.transactions if tx.get("blockTime", 0) < creation_time + 900]

        if early_txs:
            tx_counts = defaultdict(int)
            for tx in early_txs:
                tx_info = tx.get("transaction", {})
                message = tx_info.get("message", {})
                account_keys = [str(acc) for acc in message.get("accountKeys", [])]
                if account_keys:
                    tx_counts[account_keys[0]] += 1

            if tx_counts:
                max_tx = max(tx_counts.values())
                total_tx = sum(tx_counts.values())
                dominant_ratio = max_tx / total_tx

                if dominant_ratio > 0.5:
                    dominant_wallet = max(tx_counts, key=tx_counts.get)
                    if dominant_wallet not in robotic_addresses:
                        robotic_wallets.append({
                            "address": self._get_address_short(dominant_wallet),
                            "pattern": "DOMINANT_WALLET",
                            "detail": f"{max_tx}/{total_tx} ({dominant_ratio*100:.0f}%) tx in first 15 min"
                        })
                        robotic_addresses.add(dominant_wallet)

        total_balance = sum(self.current_holders.values()) if self.current_holders else 0
        robotic_balance = sum(self.current_holders.get(addr, 0) for addr in robotic_addresses)
        robotic_control = (robotic_balance / total_balance * 100) if total_balance > 0 else 0

        RISK_TABLE = [
            (50, 25),
            (30, 15),
            (15, 10),
            (5, 5),
            (0, 2 if robotic_wallets else 0)
        ]

        risk_score = next((risk for control, risk in RISK_TABLE if robotic_control >= control), 0)

        return {
            "robotic_wallets_found": len(robotic_wallets),
            "robotic_wallets": robotic_wallets,
            "total_control_percent": round(robotic_control, 2),
            "risk_score": risk_score
        }
    
    def detect_deployer_funded_snipers(self) -> Dict:
        if not self.transactions:
            return {"error": "No transactions"}

        deployer = None
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0

        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == creation_time:
                tx_info = tx.get("transaction", {})
                message = tx_info.get("message", {})
                account_keys = [str(acc) for acc in message.get("accountKeys", [])]
                if account_keys:
                    deployer = account_keys[0]
                    break
                
        if not deployer:
            return {"error": "Deployer not found"}

        funded_wallets = set()
        funding_queue = [(deployer, 0)]
        processed = set()

        while funding_queue:
            addr, hops = funding_queue.pop(0)
            if addr in processed or hops > 7:
                continue
            processed.add(addr)

            for tx in self.transactions:
                timestamp = tx.get("blockTime", 0)
                if timestamp > creation_time + 3600:
                    continue
                
                tx_info = tx.get("transaction", {})
                message = tx_info.get("message", {})
                account_keys = [str(acc) for acc in message.get("accountKeys", [])]

                if len(account_keys) >= 2 and account_keys[0] == addr:
                    receiver = account_keys[1]
                    if receiver not in funded_wallets:
                        funded_wallets.add(receiver)
                        funding_queue.append((receiver, hops + 1))

        snipers = []
        pool_set = set(self._identify_pools())

        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0 or timestamp > creation_time + 300:
                continue
            
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]

            has_pool = any(addr in pool_set for addr in account_keys)
            if not has_pool:
                continue
            
            tx_meta = tx.get("meta", {})

            for bal in tx_meta.get("postTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    if owner in funded_wallets:
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        sold_quickly = self._did_sell_quickly(owner, timestamp)

                        snipers.append({
                            "address": self._get_address_short(owner),
                            "buy_time": timestamp - creation_time,
                            "amount_percent": amount / self.total_supply * 100 if self.total_supply > 0 else 0,
                            "sold_quickly": sold_quickly
                        })

        return {
            "deployer": self._get_address_short(deployer),
            "snipers_found": len(snipers),
            "snipers": snipers[:20],
            "total_sniper_supply_percent": sum(s["amount_percent"] for s in snipers),
            "risk_score": min(len(snipers) * 10, 40)
        }
    
    def get_bot_clusters(self) -> Dict:
        if not self.current_holders:
            return {"clusters": [], "risk_score": 0}

        total_balance = sum(self.current_holders.values())
        pool_set = set(self._identify_pools())
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0

        candidates = []
        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            tx_count = self.address_activity.get(addr, 0)
            first_seen = self.first_seen.get(addr, 0)

            is_pool = self.is_liquidity_pool(addr, share, tx_count)
            if is_pool:
                continue

            is_candidate = False

            if share < 0.05 and tx_count > 20:
                is_candidate = True
            elif share < 0.15 and tx_count > 10:
                is_candidate = True
            elif share > 0.2 and tx_count < 30:
                minutes_after_start = (first_seen - creation_time) / 60 if first_seen and creation_time else 999
                if minutes_after_start < 30:
                    is_candidate = True

            if is_candidate:
                candidates.append(addr)

        time_groups = defaultdict(list)
        for addr in candidates:
            first_seen = self.first_seen.get(addr, 0)
            if first_seen:
                share = (self.current_holders.get(addr, 0) / total_balance * 100) if total_balance > 0 else 0
                interval_size = 60 if share > 0.2 else 300
                interval = int(first_seen // interval_size)
                time_groups[interval].append(addr)

        clusters = []
        total_cluster_balance = 0

        for interval, addrs in time_groups.items():
            min_size = 3 if any(self.current_holders.get(addr, 0) / total_balance * 100 > 0.2 for addr in addrs) else 5

            if len(addrs) >= min_size:
                cluster_balance = sum(self.current_holders.get(addr, 0) for addr in addrs)
                cluster_share = (cluster_balance / total_balance * 100) if total_balance > 0 else 0
                total_cluster_balance += cluster_balance

                clusters.append({
                    "size": len(addrs),
                    "created_at": datetime.fromtimestamp(interval * 60).strftime("%Y-%m-%d %H:%M:%S"),
                    "addresses": [self._get_address_short(a) for a in addrs[:5]],
                    "total_balance_millions": cluster_balance / (10 ** self.decimals) / 1_000_000,
                    "total_share_percent": round(cluster_share, 2)
                })

        sync_windows = defaultdict(set)

        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue
            
            time_window = int(timestamp // 10)

            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]

            has_pool = any(addr in pool_set for addr in account_keys)
            if not has_pool:
                continue
            
            tx_meta = tx.get("meta", {})

            for bal in tx_meta.get("postTokenBalances", []):
                if bal.get("mint") != self.token_mint:
                    continue
                
                owner = bal.get("owner", "")
                if not owner or owner in pool_set:
                    continue
                
                share = (self.current_holders.get(owner, 0) / total_balance * 100) if total_balance > 0 else 0
                if share < 0.15:
                    sync_windows[time_window].add(owner)

        synchronous_buyers = set()
        for time_window, buyers in sync_windows.items():
            if len(buyers) >= 3:
                synchronous_buyers.update(buyers)

        sync_count = len(synchronous_buyers)
        sync_balance = sum(self.current_holders.get(addr, 0) for addr in synchronous_buyers)
        sync_share = (sync_balance / total_balance * 100) if total_balance > 0 else 0

        total_cluster_share = (total_cluster_balance / total_balance * 100) if total_balance > 0 else 0
        risk_score = min(len(clusters) * 5 + (sync_count // 20) + int(total_cluster_share // 2), 35)

        return {
            "clusters_found": len(clusters),
            "clusters": clusters,
            "synchronous_buyers": sync_count,
            "synchronous_share_percent": round(sync_share, 2),
            "total_cluster_share_percent": round(total_cluster_share, 2),
            "total_cluster_balance_millions": total_cluster_balance / (10 ** self.decimals) / 1_000_000,
            "risk_score": risk_score,
            "total_suspicious": len(candidates)
        }
    
    def get_advanced_bot_analysis(self) -> Dict:
        if not self.transactions:
            return {"error": "No transactions"}

        pool_set = set(self._identify_pools())
        total_supply = self.total_supply
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0

        address_actions = defaultdict(list)

        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue

            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]

            has_pool = any(addr in pool_set for addr in account_keys)
            if not has_pool:
                continue

            tx_meta = tx.get("meta", {})

            for bal in tx_meta.get("postTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    if owner and owner not in pool_set:
                        owner_share = (self.current_holders.get(owner, 0) / sum(self.current_holders.values()) * 100) if self.current_holders else 0
                        owner_tx_count = self.address_activity.get(owner, 0)
                        if self.is_liquidity_pool(owner, owner_share, owner_tx_count):
                            continue
                        
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        if amount > 0:
                            amount_percent = amount / total_supply * 100 if total_supply > 0 else 0
                            minutes_after_start = (timestamp - creation_time) / 60 if creation_time else 0
                            address_actions[owner].append({
                                "timestamp": timestamp,
                                "type": "BUY",
                                "amount": amount,
                                "amount_percent": amount_percent,
                                "minutes_after_start": minutes_after_start
                            })

            for bal in tx_meta.get("preTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    if owner and owner not in pool_set:
                        owner_share = (self.current_holders.get(owner, 0) / sum(self.current_holders.values()) * 100) if self.current_holders else 0
                        owner_tx_count = self.address_activity.get(owner, 0)
                        if self.is_liquidity_pool(owner, owner_share, owner_tx_count):
                            continue
                        
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        if amount > 0:
                            amount_percent = amount / total_supply * 100 if total_supply > 0 else 0
                            minutes_after_start = (timestamp - creation_time) / 60 if creation_time else 0
                            address_actions[owner].append({
                                "timestamp": timestamp,
                                "type": "SELL",
                                "amount": amount,
                                "amount_percent": amount_percent,
                                "minutes_after_start": minutes_after_start
                            })

        suspicious_addresses = set()
        manipulation_patterns = []

        for addr, actions in address_actions.items():
            if len(actions) < 2:
                continue
            
            actions.sort(key=lambda x: x["timestamp"])

            for i in range(len(actions) - 1):
                if actions[i]["type"] == "BUY" and actions[i+1]["type"] == "SELL":
                    time_diff = actions[i+1]["timestamp"] - actions[i]["timestamp"]
                    if time_diff < 300:
                        buy_amount = actions[i]["amount_percent"]
                        sell_amount = actions[i+1]["amount_percent"]

                        if buy_amount > 0.05 and sell_amount > 0.05:
                            suspicious_addresses.add(addr)
                            manipulation_patterns.append({
                                "address": self._get_address_short(addr),
                                "pattern": "RAPID_BUY_SELL",
                                "time_seconds": time_diff,
                                "buy_percent": round(buy_amount, 2),
                                "sell_percent": round(sell_amount, 2),
                                "minutes_after_start": round(actions[i]["minutes_after_start"], 1)
                            })

            sells = [a for a in actions if a["type"] == "SELL" and a["amount_percent"] > 0.01]
            if len(sells) >= 5:
                total_sold = sum(s["amount_percent"] for s in sells)
                if total_sold > 0.5:
                    suspicious_addresses.add(addr)
                    manipulation_patterns.append({
                        "address": self._get_address_short(addr),
                        "pattern": "MULTIPLE_SELLS",
                        "sell_count": len(sells),
                        "total_sold_percent": round(total_sold, 2)
                    })

        time_windows = defaultdict(list)

        for addr, actions in address_actions.items():
            for action in actions:
                if action["amount_percent"] > 0.05:
                    window = int(action["timestamp"] // 10)
                    time_windows[window].append({
                        "address": addr,
                        "type": action["type"],
                        "amount_percent": action["amount_percent"]
                    })

        synchronous_manipulations = []
        for window, actions in time_windows.items():
            if len(actions) >= 3:
                buys = [a for a in actions if a["type"] == "BUY"]
                sells = [a for a in actions if a["type"] == "SELL"]

                if len(buys) >= 2 or len(sells) >= 2:
                    total_buy = sum(a["amount_percent"] for a in buys)
                    total_sell = sum(a["amount_percent"] for a in sells)

                    synchronous_manipulations.append({
                        "time_window": window * 10,
                        "buyers": len(buys),
                        "sellers": len(sells),
                        "total_buy_percent": round(total_buy, 2),
                        "total_sell_percent": round(total_sell, 2),
                        "addresses": list(set(a["address"] for a in actions))[:10]
                    })

        risk_score = 0
        if len(suspicious_addresses) > 10:
            risk_score += 20
        if len(synchronous_manipulations) > 3:
            risk_score += 25
        if len(manipulation_patterns) > 10:
            risk_score += 15

        return {
            "suspicious_addresses": len(suspicious_addresses),
            "manipulation_patterns": manipulation_patterns[:20],
            "synchronous_manipulations": synchronous_manipulations[:10],
            "risk_score": min(risk_score, 50),
            "risk_level": "HIGH" if risk_score > 35 else "MEDIUM" if risk_score > 15 else "LOW"
        }
        
    def classify_bots(self) -> Dict:
        if not self.current_holders:
            return {"error": "No holders"}

        total_balance = sum(self.current_holders.values())
        pool_set = set(self._identify_pools())
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0

        bot_candidates = []

        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            tx_count = self.address_activity.get(addr, 0)
            first_seen = self.first_seen.get(addr, 0)
            minutes_after_start = (first_seen - creation_time) / 60 if first_seen and creation_time else 999

            is_pool = self.is_liquidity_pool(addr, share, tx_count)
            if is_pool:
                continue

            is_suspicious = False
            bot_type = None
            threat_level = "LOW"

            if share < 0.05 and tx_count > 30:
                is_suspicious = True
                bot_type = "MICRO_BOT"
                threat_level = "LOW"

            elif share < 0.1 and tx_count > 10:
                for other_addr, other_share in list(self.current_holders.items())[:100]:
                    if other_addr != addr:
                        other_first = self.first_seen.get(other_addr, 0)
                        if abs(first_seen - other_first) < 300:
                            if share > 0 and other_share > 0:
                                is_suspicious = True
                                bot_type = "SYNCHRONIZED_BOT"
                                threat_level = "MEDIUM"
                                break

            elif share > 0.2 and tx_count < 30:
                if minutes_after_start < 30:
                    is_suspicious = True
                    if share > 3:
                        bot_type = "MEGA_WHALE_BOT"
                        threat_level = "CRITICAL"
                    elif share > 1:
                        bot_type = "WHALE_BOT"
                        threat_level = "HIGH"
                    else:
                        bot_type = "MINNOW_BOT"
                        threat_level = "MEDIUM"

            elif share < 1 and tx_count > 100:
                is_suspicious = True
                bot_type = "WASH_TRADING_BOT"
                threat_level = "MEDIUM"

            if is_suspicious:
                bot_candidates.append({
                    "address": self._get_address_short(addr),
                    "share_percent": round(share, 2),
                    "tx_count": tx_count,
                    "first_seen_minutes": round(minutes_after_start, 1),
                    "type": bot_type,
                    "threat_level": threat_level
                })

        classification = {
            "MICRO_BOT": {"count": 0, "total_share": 0, "addresses": [], "threat": "LOW", "description": "Micro bots with many transactions"},
            "SYNCHRONIZED_BOT": {"count": 0, "total_share": 0, "addresses": [], "threat": "MEDIUM", "description": "Synchronized bots created at same time"},
            "MINNOW_BOT": {"count": 0, "total_share": 0, "addresses": [], "threat": "MEDIUM", "description": "Small whales (0.2-1%) bought early"},
            "WHALE_BOT": {"count": 0, "total_share": 0, "addresses": [], "threat": "HIGH", "description": "Large bots (1-3%) bought early"},
            "MEGA_WHALE_BOT": {"count": 0, "total_share": 0, "addresses": [], "threat": "CRITICAL", "description": "Very large bots (>3%) organizers"},
            "WASH_TRADING_BOT": {"count": 0, "total_share": 0, "addresses": [], "threat": "MEDIUM", "description": "Wash trading bots"}
        }

        for bot in bot_candidates:
            bot_type = bot["type"]
            if bot_type in classification:
                classification[bot_type]["count"] += 1
                classification[bot_type]["total_share"] += bot["share_percent"]
                if len(classification[bot_type]["addresses"]) < 20:
                    classification[bot_type]["addresses"].append(bot["address"])

        for bot_type in classification:
            classification[bot_type]["total_share"] = round(classification[bot_type]["total_share"], 2)

        total_bot_share = sum(c["total_share"] for c in classification.values())
        total_bot_count = sum(c["count"] for c in classification.values())

        risk_score = 0
        risk_score += classification["MEGA_WHALE_BOT"]["total_share"] * 3
        risk_score += classification["WHALE_BOT"]["total_share"] * 2
        risk_score += classification["MINNOW_BOT"]["total_share"] * 1
        risk_score += classification["SYNCHRONIZED_BOT"]["total_share"] * 1
        risk_score += classification["WASH_TRADING_BOT"]["total_share"] * 0.5
        risk_score += min(classification["MICRO_BOT"]["count"] / 10, 15)

        risk_score = min(int(risk_score), 100)

        if risk_score >= 60:
            overall_risk = "CRITICAL"
            recommendation = "Very large whale bots detected, high scam risk"
        elif risk_score >= 35:
            overall_risk = "HIGH"
            recommendation = "Large bots detected, likely manipulation"
        elif risk_score >= 15:
            overall_risk = "MEDIUM"
            recommendation = "Bot farmers present"
        else:
            overall_risk = "LOW"
            recommendation = "Minor bot activity"

        return {
            "total_bots": total_bot_count,
            "total_bot_share_percent": round(total_bot_share, 2),
            "classification": classification,
            "risk_score": risk_score,
            "overall_risk": overall_risk,
            "recommendation": recommendation,
            "top_bots": bot_candidates[:20]
        }
        
    def calculate_suspicious_supply_index(self) -> Dict:
        if not self.current_holders:
            return {"error": "No holders"}
    
        total_balance = sum(self.current_holders.values())
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0
    
        categories = {
            "insider_snipers": {"wallets": [], "supply": 0},
            "cluster_bots": {"wallets": [], "supply": 0},
            "rapid_sellers": {"wallets": [], "supply": 0},
            "suspicious_whales": {"wallets": [], "supply": 0},
            "coordinated_actors": {"wallets": [], "supply": 0}
        }
    
        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            tx_count = self.address_activity.get(addr, 0)
            first_seen = self.first_seen.get(addr, 0)
            minutes_after_start = (first_seen - creation_time) / 60 if first_seen and creation_time else 999
    
            is_pool = self.is_liquidity_pool(addr, share, tx_count)
            if is_pool:
                continue
            
            category = None
    
            if minutes_after_start < 5 and share > 0.05:
                category = "insider_snipers"
            elif self._is_rapid_seller(addr, creation_time):
                category = "rapid_sellers"
            elif self._is_in_cluster(addr):
                category = "cluster_bots"
            elif share > 0.3 and tx_count < 20 and minutes_after_start < 60:
                category = "suspicious_whales"
            elif self._is_coordinated(addr):
                category = "coordinated_actors"
    
            if category:
                categories[category]["wallets"].append(addr)
                categories[category]["supply"] += balance
    
        total_suspicious_supply = 0
        for cat in categories:
            supply_percent = (categories[cat]["supply"] / total_balance * 100) if total_balance > 0 else 0
            categories[cat]["supply_percent"] = round(supply_percent, 2)
            total_suspicious_supply += categories[cat]["supply"]
    
        total_suspicious_percent = (total_suspicious_supply / total_balance * 100) if total_balance > 0 else 0
        total_suspicious_wallets = sum(len(c["wallets"]) for c in categories.values())
    
        if total_suspicious_percent >= 50:
            risk_level = "CRITICAL"
            recommendation = "STRONG AVOID - More than 50% supply controlled by suspicious wallets"
        elif total_suspicious_percent >= 20:
            risk_level = "CRITICAL"
            recommendation = "STRONG AVOID - More than 20% supply controlled by suspicious wallets"
        elif total_suspicious_percent >= 10:
            risk_level = "HIGH"
            recommendation = "AVOID - Significant supply controlled by suspicious wallets"
        elif total_suspicious_percent >= 5:
            risk_level = "MEDIUM"
            recommendation = "CAUTION - Suspicious wallets present"
        else:
            risk_level = "LOW"
            recommendation = "POTENTIAL - Minor suspicious activity"
    
        return {
            "suspicious_supply_percent": round(total_suspicious_percent, 1),
            "risk_level": risk_level,
            "recommendation": recommendation,
            "categories": categories,
            "total_suspicious_wallets": total_suspicious_wallets
        }

    def get_wash_trading(self) -> Dict:
        address_pairs = defaultdict(int)

        for tx in self.transactions:
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]

            if len(account_keys) >= 2:
                sender = account_keys[0]
                receiver = account_keys[1]
                pair = tuple(sorted([sender, receiver]))
                address_pairs[pair] += 1
                
        suspicious_pairs = []
        for pair, count in address_pairs.items():
            if count > 5: 
                suspicious_pairs.append({
                    "addresses": [self._get_address_short(p) for p in pair],
                    "tx_count": count
                })

        is_wash = len(suspicious_pairs) > 3  
        risk_score = 25 if is_wash else 0  

        return {
            "is_wash_trading": is_wash,
            "suspicious_pairs": len(suspicious_pairs),
            "risk_score": risk_score
        }

    def get_price_volume_correlation(self) -> Dict:
        total_buy = sum(self.buy_volume.values())
        total_sell = sum(self.sell_volume.values())
        
        if total_buy > total_sell * 1.5:
            correlation = "POSITIVE"
            risk = 0
        elif total_sell > total_buy * 1.5:
            correlation = "NEGATIVE"
            risk = 20
        else:
            correlation = "NEUTRAL"
            risk = 5
        
        return {
            "correlation": correlation,
            "risk_score": risk,
            "note": "Buy volume vs Sell volume ratio"
        }
    
    def get_deployer_behavior(self) -> Dict:
        if not self.tx_timestamps:
            return {"error": "No data"}
        
        creation_time = min(self.tx_timestamps)
        
        deployer = None
        for tx in self.transactions:
            if tx.get("blockTime", 0) == creation_time:
                tx_info = tx.get("transaction", {})
                message = tx_info.get("message", {})
                account_keys = [str(acc) for acc in message.get("accountKeys", [])]
                if account_keys:
                    deployer = account_keys[0]
                    break
        
        if not deployer:
            return {"error": "Deployer not found"}
        
        deployer_sells = 0
        deployer_sell_volume = 0
        migration_ts = self.migration_time if self.migration_time else creation_time + 3600
        
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]
            
            if deployer in account_keys and timestamp < migration_ts:
                meta = tx.get("meta", {})
                for bal in meta.get("preTokenBalances", []):
                    if bal.get("mint") == self.token_mint:
                        owner = bal.get("owner", "")
                        if owner == deployer:
                            amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                            if amount > 0:
                                deployer_sells += 1
                                deployer_sell_volume += amount
        
        if deployer_sells > 0:
            behavior = "SOLD_BEFORE_MIGRATION"
            risk = 0
        else:
            behavior = "HELD"
            risk = 0
        
        return {
            "deployer": self._get_address_short(deployer),
            "sells_before_migration": deployer_sells,
            "sell_volume_millions": deployer_sell_volume / (10 ** self.decimals) / 1_000_000,
            "behavior": behavior,
            "risk_score": risk
        }
    
    def get_early_buyers(self, minutes: int = 15) -> Dict:
        if not self.tx_timestamps or not self.migration_time:
            return {"error": "No data or migration time"}
        
        creation_time = min(self.tx_timestamps)
        creation_dt = datetime.fromtimestamp(creation_time)
        early_cutoff = creation_dt + timedelta(minutes=minutes)
        migration_dt = datetime.fromtimestamp(self.migration_time)
        
        pool_addresses = self._identify_pools()
        early_holders = {}
        
        for tx in self.transactions:
            timestamp = tx.get("blockTime", 0)
            if timestamp == 0:
                continue
            
            dt = datetime.fromtimestamp(timestamp)
            if dt >= migration_dt:
                continue
            
            tx_meta = tx.get("meta", {})
            tx_info = tx.get("transaction", {})
            message = tx_info.get("message", {})
            account_keys = [str(acc) for acc in message.get("accountKeys", [])]
            has_pool = any(addr in pool_addresses for addr in account_keys)
            
            if not has_pool:
                continue
            
            for bal in tx_meta.get("postTokenBalances", []):
                if bal.get("mint") == self.token_mint:
                    owner = bal.get("owner", "")
                    amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                    if owner and amount > 0 and owner not in pool_addresses:
                        if owner not in early_holders:
                            early_holders[owner] = {"initial": 0, "current": 0}
                        early_holders[owner]["initial"] += amount
        
        for addr in early_holders:
            early_holders[addr]["current"] = self.current_holders.get(addr, 0)
        
        total_initial = sum(h["initial"] for h in early_holders.values())
        total_current = sum(h["current"] for h in early_holders.values())
        retention_rate = (total_current / total_initial * 100) if total_initial > 0 else 0
        
        holders_list = []
        for addr, data in early_holders.items():
            share = (data["initial"] / total_initial * 100) if total_initial > 0 else 0
            retention = (data["current"] / data["initial"] * 100) if data["initial"] > 0 else 0
            holders_list.append({
                "address": self._get_address_short(addr),
                "initial_millions": data["initial"] / (10 ** self.decimals) / 1_000_000,
                "current_millions": data["current"] / (10 ** self.decimals) / 1_000_000,
                "share_percentage": round(share, 2),
                "retention_percentage": round(retention, 1)
            })
        
        holders_list.sort(key=lambda x: x["initial_millions"], reverse=True)
        
        full_sellers = [h for h in holders_list if h["retention_percentage"] == 0]
        partial_sellers = [h for h in holders_list if 0 < h["retention_percentage"] < 50]
        
        return {
            "creation_time": creation_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "migration_time": migration_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "cutoff_minutes": minutes,
            "total_early_holders": len(holders_list),
            "total_initial_volume_millions": total_initial / (10 ** self.decimals) / 1_000_000,
            "total_current_volume_millions": total_current / (10 ** self.decimals) / 1_000_000,
            "retention_rate": round(retention_rate, 1),
            "full_sellers_count": len(full_sellers),
            "partial_sellers_count": len(partial_sellers),
            "top_early_holders": holders_list[:15]
        }
    
    def get_pre_migration_analysis(self) -> Dict:
        if not self.migration_time:
            return {"error": "No migration found"}
        
        migration_ts = self.migration_time
        if isinstance(migration_ts, datetime):
            migration_ts = migration_ts.timestamp()
        
        pre_txs = [tx for tx in self.transactions if tx.get("blockTime", 0) < migration_ts]
        
        minutes_before = [60, 30, 15, 10, 5, 3, 1]
        growth_patterns = {}
        
        for minutes in minutes_before:
            cutoff = migration_ts - (minutes * 60)
            txs_in_window = [tx for tx in pre_txs if tx.get("blockTime", 0) >= cutoff]
            
            unique_holders = set()
            volume = 0
            for tx in txs_in_window:
                tx_meta = tx.get("meta", {})
                for bal in tx_meta.get("postTokenBalances", []):
                    if bal.get("mint") == self.token_mint:
                        owner = bal.get("owner", "")
                        if owner:
                            unique_holders.add(owner)
                
                for bal in tx_meta.get("preTokenBalances", []):
                    if bal.get("mint") == self.token_mint:
                        owner = bal.get("owner", "")
                        amount = int(bal.get("uiTokenAmount", {}).get("amount", 0))
                        if owner and amount > 0:
                            volume += amount
            
            growth_patterns[f"{minutes}_min"] = {
                "holders": len(unique_holders),
                "volume_millions": volume / (10 ** self.decimals) / 1_000_000,
                "holder_growth_rate": len(unique_holders) / minutes if minutes > 0 else 0
            }
        
        last_5min = growth_patterns.get("5_min", {}).get("holders", 0)
        last_1min = growth_patterns.get("1_min", {}).get("holders", 0)
        last_5min_volume = growth_patterns.get("5_min", {}).get("volume_millions", 0)
        last_1min_volume = growth_patterns.get("1_min", {}).get("volume_millions", 0)
        
        if last_1min > last_5min * 0.8:
            pattern = "EXPLOSIVE_LAST_MINUTE"
            risk = 30
        elif last_5min > 50:
            pattern = "EXTREME_ACCELERATION"
            risk = 25
        elif last_5min > 20:
            pattern = "HIGH_ACCELERATION"
            risk = 15
        elif last_5min > 5:
            pattern = "NORMAL_GROWTH"
            risk = 5
        else:
            pattern = "LOW_ACTIVITY"
            risk = 0
        
        return {
            "growth_patterns": growth_patterns,
            "pattern_type": pattern,
            "risk_score": risk,
            "pre_migration_transactions": len(pre_txs),
            "last_5min_volume_millions": round(last_5min_volume, 2),
            "last_1min_volume_millions": round(last_1min_volume, 2)
        }
    
    def get_migration_speed_analysis(self) -> Dict:
        if not self.tx_timestamps or not self.migration_time:
            return {"error": "No data"}
        
        creation_time = min(self.tx_timestamps)
        migration_time = self.migration_time
        
        seconds_to_migrate = migration_time - creation_time
        
        if seconds_to_migrate < 60:
            risk = 40
            verdict = "INSTANT_MIGRATION"
        elif seconds_to_migrate < 300:
            risk = 25
            verdict = "VERY_FAST_MIGRATION"
        elif seconds_to_migrate < 3600:
            risk = 10
            verdict = "FAST_MIGRATION"
        else:
            risk = 0
            verdict = "NORMAL_MIGRATION_TIMEFRAME"
        
        return {
            "creation_time": datetime.fromtimestamp(creation_time).strftime("%Y-%m-%d %H:%M:%S"),
            "migration_time": datetime.fromtimestamp(migration_time).strftime("%Y-%m-%d %H:%M:%S"),
            "seconds_to_migrate": int(seconds_to_migrate),
            "risk_score": risk,
            "verdict": verdict
        }
        
    def get_robotic_control_percent(self) -> float:
        robotic = self.detect_robotic_patterns()
        if "error" in robotic or not robotic.get("robotic_wallets_found", 0):
            return 0.0

        robotic_addresses = set()
        for wallet in robotic.get("robotic_wallets", []):
            short_addr = wallet.get("address", "")
            for addr, balance in self.current_holders.items():
                if addr[:4] == short_addr:
                    robotic_addresses.add(addr)
                    break
                
        total_balance = sum(self.current_holders.values())
        robotic_balance = sum(self.current_holders.get(addr, 0) for addr in robotic_addresses)

        return (robotic_balance / total_balance * 100) if total_balance > 0 else 0.0
        
    def get_bot_risk_summary(self) -> Dict:
        classification = self.classify_bots()
        clusters = self.get_bot_clusters()
        robotic = self.detect_robotic_patterns()

        bot_control = classification.get("total_bot_share_percent", 0)
        bot_count = classification.get("total_bots", 0)
        cluster_count = clusters.get("clusters_found", 0)
        robotic_count = robotic.get("robotic_wallets_found", 0)

        rules = [
            (30, 70, "CRITICAL"),
            (20, 50, "VERY_HIGH"),
            (15, 40, "HIGH"),
            (10, 30, "MEDIUM"),
            (5, 20, "LOW"),
        ]

        threat_score = 0
        threat_level = "MINIMAL"

        for threshold, score, level in rules:
            if bot_control >= threshold:
                threat_score = score
                threat_level = level
                break
        else:
            if bot_count > 50:
                threat_score = 15
                threat_level = "MANY_BUT_SMALL"
            elif bot_count > 20:
                threat_score = 10
                threat_level = "NOTICEABLE"

        return {
            "threat_level": threat_level,
            "threat_score": threat_score,
            "bot_control_percent": bot_control,
            "bot_count": bot_count,
            "cluster_count": cluster_count,
            "robotic_count": robotic_count,
            "assessment": f"{bot_count} bots control {bot_control}% of supply"
        }
    
    def get_quick_summary(self, force_full: bool = False) -> Dict:
        """Быстрый анализ - всегда использует полные данные без сэмплирования"""
        self._ensure_initialized()

        if force_full:
            return self.get_full_analysis(save_history=False)

        if self._redis and self._cache_key:
            try:
                quick_cache = self._redis.get(f"{self._cache_key}:quick_summary")
                if quick_cache:
                    return json.loads(quick_cache)
            except Exception:
                pass
            
        # УБИРАЕМ проверку на 2000 транзакций - всегда делаем полный анализ
        # Вместо сэмплирования используем все данные
        anti_frag = self.get_anti_fragmentation()

        total_balance = sum(self.current_holders.values()) if self.current_holders else 0
        creation_time = min(self.tx_timestamps) if self.tx_timestamps else 0

        # Подсчет ботов (микродоли)
        bot_count = 0
        bot_balance = 0
        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            if share < 0.05:
                bot_count += 1
                bot_balance += balance

        # Инсайдеры (покупатели в первые 5 минут)
        insider_count = 0
        for addr, first_seen in self.first_seen.items():
            if first_seen and creation_time:
                minutes_after = (first_seen - creation_time) / 60
                if minutes_after < 5:
                    insider_count += 1

        # Подсчет пулов
        pools = []
        for addr, balance in self.current_holders.items():
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            tx_count = self.address_activity.get(addr, 0)
            if self.is_liquidity_pool(addr, share, tx_count):
                pools.append(addr)

        total_buy_vol = sum(self.buy_volume.values()) / (10 ** self.decimals) if self.buy_volume else 0
        total_sell_vol = sum(self.sell_volume.values()) / (10 ** self.decimals) if self.sell_volume else 0

        malicious = self.get_malicious_supply_index()
        sell_pressure = self.get_sell_pressure_index()
        whale_acc = self.get_whale_accumulation_rate()
        migration_speed = self.get_migration_speed_analysis()

        total_holders = anti_frag.get("total_holders_reported", len(self.current_holders))
        real_holders = anti_frag.get("estimated_real_holders", 0)
        artificial_inflation = anti_frag.get("artificial_inflation_percent", 0)

        result = {
            "token_mint": self.token_mint[:16],
            "total_supply_millions": round(self.total_supply_formatted / 1_000_000, 2),

            "total_holders": total_holders,
            "real_holders": real_holders,
            "fake_holders_percent": round(artificial_inflation, 1),
            "fake_holders_count": total_holders - real_holders,
            "suspicious_count": insider_count,

            "malicious_supply_percent": malicious.get("malicious_supply_percent", 0),

            "bots_count": bot_count,
            "bots_control_percent": round((bot_balance / max(1, total_balance) * 100), 2),

            "insiders_count": insider_count,
            "insiders_control_percent": round((insider_count / max(1, len(self.current_holders)) * 100), 2),

            "pools_count": len(pools),
            "total_transactions": len(self.transactions),

            "creation_time": datetime.fromtimestamp(creation_time).strftime("%Y-%m-%d %H:%M:%S") if creation_time else "Unknown",
            "migration_time": datetime.fromtimestamp(self.migration_time).strftime("%Y-%m-%d %H:%M:%S") if self.migration_time else "Not migrated",

            "total_buy_volume": round(total_buy_vol, 2),
            "total_sell_volume": round(total_sell_vol, 2),
            "net_volume": round(total_buy_vol - total_sell_vol, 2),

            "sell_buy_ratio": sell_pressure.get("ratio", 0),
            "sell_pressure": sell_pressure.get("pressure", "LOW"),
            "whale_accumulation": whale_acc.get("rate_percent", 0),
            "whale_trend": whale_acc.get("trend", "STABLE"),
            "migration_verdict": migration_speed.get("verdict", "N/A"),
            "migration_seconds": migration_speed.get("seconds_to_migrate"),
            "migration_risk": migration_speed.get("risk_score", 0),

            "analysis_mode": "full_data",
            "sample_size": len(self.transactions)
        }

        if self._redis and self._cache_key:
            try:
                self._redis.setex(f"{self._cache_key}:quick_summary", 300, json.dumps(result, default=str))
            except Exception:
                pass
            
        return result
    
    @_cached_method(ttl=600)
    def get_hard_risk_score(self) -> Dict:
        risk_score = 0
        anomalies = []

        early = self.get_early_buyers(15)
        if "error" not in early:
            retention_rate = early.get("retention_rate", 100)
            if retention_rate < 50:
                early_risk = int(20 * (50 - retention_rate) / 50)
                risk_score += early_risk
                anomalies.append({
                    "type": "EARLY_HOLDERS_DUMPED",
                    "detail": f"Retention rate: {retention_rate}%",
                    "score": early_risk
                })

        migration_speed = self.get_migration_speed_analysis()
        if "error" not in migration_speed and migration_speed.get("risk_score", 0) >= 25:
            risk_score += migration_speed["risk_score"]
            anomalies.append({
                "type": migration_speed.get("verdict", ""),
                "detail": f"Migrated in {migration_speed.get('seconds_to_migrate', 0)} seconds",
                "score": migration_speed["risk_score"]
            })

        pre_migration = self.get_pre_migration_analysis()
        if "error" not in pre_migration and pre_migration.get("risk_score", 0) >= 15:
            risk_score += pre_migration["risk_score"]
            anomalies.append({
                "type": pre_migration.get("pattern_type", ""),
                "detail": "Holder growth pattern before migration",
                "score": pre_migration["risk_score"]
            })

        sell_pressure = self.get_sell_pressure_index()
        if sell_pressure.get("risk_score", 0) > 0:
            risk_score += sell_pressure["risk_score"]
            anomalies.append({
                "type": f"SELL_PRESSURE_{sell_pressure.get('pressure', '')}",
                "detail": f"Sell/Buy ratio: {sell_pressure.get('ratio', 0)}",
                "score": sell_pressure["risk_score"]
            })

        correlation = self.get_price_volume_correlation()
        if correlation.get("risk_score", 0) > 0:
            risk_score += correlation["risk_score"]
            anomalies.append({
                "type": f"PRICE_VOLUME_{correlation.get('correlation', '')}",
                "detail": correlation.get("note", ""),
                "score": correlation["risk_score"]
            })

        whale = self.get_whale_accumulation_rate()
        if whale.get("risk_score", 0) > 0:
            risk_score += whale["risk_score"]
            anomalies.append({
                "type": f"WHALE_{whale.get('trend', '')}",
                "detail": f"Change: {whale.get('rate_percent', 0)}%",
                "score": whale["risk_score"]
            })

        malicious = self.get_malicious_supply_index()
        if "error" not in malicious:
            malicious_percent = malicious.get("malicious_supply_percent", 0)

            if malicious_percent >= 50:
                malicious_risk = 70
            elif malicious_percent >= 30:
                malicious_risk = 50
            elif malicious_percent >= 15:
                malicious_risk = 30
            elif malicious_percent >= 5:
                malicious_risk = 15
            else:
                malicious_risk = 0

            if malicious_risk > 0:
                risk_score += malicious_risk
                anomalies.append({
                    "type": "MALICIOUS_BOTS",
                    "detail": f"{malicious_percent}% supply controlled by malicious wallets",
                    "score": malicious_risk
                })

        snipers = self.detect_deployer_funded_snipers()
        if "error" not in snipers and snipers.get("snipers_found", 0) > 0:
            sniper_share = snipers.get("total_sniper_supply_percent", 0)
            if sniper_share > 10:
                sniper_risk = 40
            elif sniper_share > 5:
                sniper_risk = 25
            elif sniper_share > 1:
                sniper_risk = 10
            else:
                sniper_risk = 0

            if sniper_risk > 0:
                risk_score += sniper_risk
                anomalies.append({
                    "type": "DEPLOYER_FUNDED_SNIPERS",
                    "detail": f"{snipers.get('snipers_found', 0)} snipers control {sniper_share:.1f}%",
                    "score": sniper_risk
                })

        robotic = self.detect_robotic_patterns()
        if "error" not in robotic and robotic.get("robotic_wallets_found", 0) > 0:
            robotic_control = robotic.get("total_control_percent", 0)

            if robotic_control >= 50:
                robotic_risk = 25
            elif robotic_control >= 30:
                robotic_risk = 15
            elif robotic_control >= 15:
                robotic_risk = 10
            elif robotic_control >= 5:
                robotic_risk = 5
            else:
                robotic_risk = 2

            if robotic_risk > 0:
                risk_score += robotic_risk
                anomalies.append({
                    "type": "ROBOTIC_PATTERNS",
                    "detail": f"{robotic.get('robotic_wallets_found', 0)} wallets control {robotic_control:.1f}%",
                    "score": robotic_risk
                })

        mm_share = self.get_market_maker_share()
        if mm_share > 0:
            mm_bonus = min(mm_share * 0.5, 15)
            risk_score = max(0, risk_score - mm_bonus)
            anomalies.append({
                "type": "MARKET_MAKER_BONUS",
                "detail": f"Market makers control {mm_share:.1f}% supply, reducing risk by {mm_bonus:.0f} points",
                "score": -int(mm_bonus)
            })

        final_score = min(risk_score, 100)

        if final_score >= 60:
            level = "CRITICAL"
            recommendation = "STRONG AVOID"
            color = "red"
        elif final_score >= 35:
            level = "HIGH"
            recommendation = "AVOID"
            color = "orange"
        elif final_score >= 15:
            level = "MEDIUM"
            recommendation = "CAUTION"
            color = "yellow"
        else:
            level = "LOW"
            recommendation = "POTENTIAL"
            color = "green"

        return {
            "score": final_score,
            "level": level,
            "recommendation": recommendation,
            "color": color,
            "anomalies": anomalies,
            "anomalies_count": len(anomalies)
        }
    
    def get_full_analysis(self, save_history: bool = False, force_full: bool = False) -> Dict:
        """Полный анализ всех метрик"""
        self._ensure_initialized()

        if self._redis and self._cache_key and not force_full:
            try:
                full_cache = self._redis.get(f"{self._cache_key}:full_analysis")
                if full_cache:
                    cached_result = json.loads(full_cache)
                    if not save_history:
                        return cached_result
            except Exception:
                pass
            
        # Получаем ВСЕ метрики (старые и новые)
        revolutionary_metrics = self.get_revolutionary_risk_score()

        # Формируем результат со ВСЕМИ полями, которые ожидает фронтенд
        result = {
            # Базовые метрики (ожидаются фронтендом)
            "token_mint": self.token_mint,
            "summary": self.get_quick_summary(force_full=False),

            # Топ холдеры
            "top_15_holders": self.get_top_holders_full(15),
            "top_15_pre_migration_holders": self.get_pre_migration_top_holders(15, min_share=0.03),
            "historical_holders": self.get_historical_holders(),

            # Временные метрики
            "early_buyers_15min": self.get_early_buyers(15),
            "pre_migration": self.get_pre_migration_analysis(),
            "migration_speed": self.get_migration_speed_analysis(),

            # Поведенческие метрики
            "whale_accumulation": self.get_whale_accumulation_rate(),
            "sell_pressure": self.get_sell_pressure_index(),
            "price_volume_correlation": self.get_price_volume_correlation(),
            "deployer_behavior": self.get_deployer_behavior(),

            # Бот-метрики
            "bot_clusters": self.get_bot_clusters(),
            "bot_classification": self.classify_bots(),
            "bot_risk_summary": self.get_bot_risk_summary(),
            "advanced_bot_analysis": self.get_advanced_bot_analysis(),
            "robotic_patterns": self.detect_robotic_patterns(),

            # Индексы риска
            "malicious_supply_index": self.get_malicious_supply_index(),
            "suspicious_supply_index": self.calculate_suspicious_supply_index(),

            # Детекторы
            "deployer_funded_snipers": self.detect_deployer_funded_snipers(),
            "wash_trading": self.get_wash_trading(),
            "market_maker_share": self.get_market_maker_share(),

            # Оценка риска
            "risk_assessment": self.get_hard_risk_score(),

            # тестовые мтерики 
            "revolutionary_metrics": revolutionary_metrics,
            "temporal_entropy": self.get_temporal_entropy(),
            "anti_fragmentation": self.get_anti_fragmentation(),
            "domino_effect": self.get_domino_effect(),
            "migration_footprint": self.get_migration_footprint(),
            "herding_index": self.get_herding_index(),

            "analyzed_at": datetime.now().isoformat(),
            "analysis_mode": "full_with_revolutionary"
        }

        # Кэшируем результат
        if self._redis and self._cache_key:
            try:
                self._redis.setex(f"{self._cache_key}:full_analysis", 3600, 
                                 json.dumps(self._to_native(result), default=str))
            except Exception:
                pass
            
        if save_history:
            self._save_to_history_sync(result)

        return result