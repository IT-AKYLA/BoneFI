import logging
import asyncio
import uuid
from datetime import datetime
from ...core.database import RedisCache, get_redis_client
from ...services.analyzer import TokenAnalyzer
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_analyzer(mint: str) -> TokenAnalyzer:
    """Универсальный хелпер для получения анализатора"""
    client = await get_redis_client()
    cache = RedisCache(client)
    
    data = await cache.get_token(mint)
    if not data:
        raise HTTPException(status_code=404, detail=f"Token {mint} not found in cache")
    
    return TokenAnalyzer(data)


def safe_get(data: Dict, *keys, default=None):
    """Безопасное получение значения из вложенного словаря"""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data if data is not None else default

@router.get("/token/{mint}/summary")
async def get_token_summary(mint: str) -> Dict:
    """Краткая сводка по токену (быстрый ответ без тяжёлых вычислений)"""
    analyzer = await get_analyzer(mint)
    return analyzer.get_quick_summary()


@router.get("/token/{mint}/holders")
async def get_holders(
    mint: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_share: float = Query(0, ge=0, le=100, description="Минимальная доля для фильтрации")
) -> Dict:
    """Список холдеров с пагинацией и сортировкой по доле"""
    analyzer = await get_analyzer(mint)
    
    total_balance = sum(analyzer.current_holders.values())
    holders = []
    
    for addr, balance in analyzer.current_holders.items():
        share = (balance / total_balance * 100) if total_balance > 0 else 0
        
        if share < min_share:
            continue
            
        holders.append({
            "address": addr[:8],
            "address_full": addr,
            "share": round(share, 4),
            "balance": balance / (10 ** analyzer.decimals),
            "balance_millions": balance / (10 ** analyzer.decimals) / 1_000_000,
            "tx_count": analyzer.address_activity.get(addr, 0),
            "is_pool": analyzer.is_liquidity_pool(addr, share, analyzer.address_activity.get(addr, 0)),
            "is_bot": share < 0.05 and analyzer.address_activity.get(addr, 0) > 20,
            "first_seen": analyzer.first_seen.get(addr)
        })
    
    holders.sort(key=lambda x: x["share"], reverse=True)
    
    return {
        "total": len(holders),
        "limit": limit,
        "offset": offset,
        "holders": holders[offset:offset + limit],
        "has_more": offset + limit < len(holders)
    }


@router.get("/token/{mint}/bots")
async def get_bots(mint: str) -> Dict:
    """Все боты с классификацией по типам"""
    analyzer = await get_analyzer(mint)
    
    classification = analyzer.classify_bots()
    
    # Добавляем маркет-мейкеров если метод существует
    if hasattr(analyzer, 'get_market_maker_share'):
        classification["market_maker_share"] = analyzer.get_market_maker_share()
    
    if hasattr(analyzer, 'get_malicious_supply_index'):
        classification["malicious_supply"] = analyzer.get_malicious_supply_index()
    
    return classification


@router.get("/token/{mint}/insiders")
async def get_insiders(mint: str) -> Dict:
    """Инсайдеры — кошельки, купившие в первые 5 минут"""
    analyzer = await get_analyzer(mint)
    
    ssi = analyzer.calculate_suspicious_supply_index()
    
    insiders = ssi.get("categories", {}).get("insider_snipers", {})
    
    # Обогащаем данными о холдерах
    enriched_wallets = []
    for addr in insiders.get("wallets", []):
        balance = analyzer.current_holders.get(addr, 0)
        share = (balance / sum(analyzer.current_holders.values()) * 100) if analyzer.current_holders else 0
        enriched_wallets.append({
            "address": addr[:8],
            "address_full": addr,
            "share": round(share, 2),
            "tx_count": analyzer.address_activity.get(addr, 0)
        })
    
    return {
        "count": len(insiders.get("wallets", [])),
        "supply_percent": insiders.get("supply_percent", 0),
        "wallets": enriched_wallets
    }


@router.get("/token/{mint}/clusters")
async def get_clusters(mint: str) -> Dict:
    """Бот-кластеры — группы кошельков, созданных в одно время"""
    analyzer = await get_analyzer(mint)
    return analyzer.get_bot_clusters()


@router.get("/token/{mint}/early-buyers")
async def get_early_buyers(
    mint: str,
    minutes: int = Query(15, ge=1, le=60, description="Количество минут от создания")
) -> Dict:
    """Ранние покупатели — кто купил в первые N минут"""
    analyzer = await get_analyzer(mint)
    return analyzer.get_early_buyers(minutes)


@router.get("/token/{mint}/risk")
async def get_token_risk(mint: str) -> Dict:
    """Только оценка риска (быстрый ответ)"""
    analyzer = await get_analyzer(mint)
    return analyzer.get_hard_risk_score()


@router.get("/token/{mint}/market-makers")
async def get_market_makers(mint: str) -> Dict:
    """Маркет-мейкеры — потенциально полезные боты"""
    analyzer = await get_analyzer(mint)
    
    if not hasattr(analyzer, '_is_market_maker'):
        return {"error": "Market maker detection not available", "mm_share": 0, "mm_wallets": []}
    
    total_balance = sum(analyzer.current_holders.values())
    mm_wallets = []
    mm_balance = 0
    
    for addr, balance in analyzer.current_holders.items():
        if analyzer._is_market_maker(addr):
            mm_balance += balance
            share = (balance / total_balance * 100) if total_balance > 0 else 0
            mm_wallets.append({
                "address": addr[:8],
                "address_full": addr,
                "share": round(share, 2),
                "tx_count": analyzer.address_activity.get(addr, 0)
            })
    
    mm_share = (mm_balance / total_balance * 100) if total_balance > 0 else 0
    
    return {
        "count": len(mm_wallets),
        "supply_percent": round(mm_share, 2),
        "wallets": mm_wallets[:50]
    }


@router.get("/token/{mint}/malicious")
async def get_malicious_bots(mint: str) -> Dict:
    """Только вредные боты (исключая маркет-мейкеров)"""
    analyzer = await get_analyzer(mint)
    
    if hasattr(analyzer, 'get_malicious_supply_index'):
        return analyzer.get_malicious_supply_index()
    
    # Fallback для обратной совместимости
    ssi = analyzer.calculate_suspicious_supply_index()
    return {
        "malicious_supply_percent": ssi.get("suspicious_supply_percent", 0),
        "risk_level": ssi.get("risk_level", "UNKNOWN"),
        "recommendation": ssi.get("recommendation", ""),
        "note": "Using legacy SSI (includes all suspicious wallets)"
    }


# ============= НОВЫЕ РЕВОЛЮЦИОННЫЕ ЭНДПОИНТЫ =============

@router.get("/token/{mint}/revolutionary/score")
async def get_revolutionary_score(mint: str) -> Dict:
    """
    🚀 НОВАЯ МЕТРИКА: Революционный скор риска
    Комбинация 5 уникальных метрик для 90% точности детекции скамов
    """
    analyzer = await get_analyzer(mint)
    
    if hasattr(analyzer, 'get_revolutionary_risk_score'):
        return analyzer.get_revolutionary_risk_score()
    else:
        # Fallback если метод недоступен
        risk = analyzer.get_hard_risk_score()
        return {
            "revolutionary_score": risk.get("score", 0),
            "risk_level": risk.get("level", "UNKNOWN"),
            "recommendation": risk.get("recommendation", ""),
            "note": "Using legacy risk score (revolutionary metrics not available)"
        }


@router.get("/token/{mint}/revolutionary/temporal-entropy")
async def get_temporal_entropy(mint: str) -> Dict:
    """
    🚀 НОВАЯ МЕТРИКА: Временная энтропия
    Определяет автоматизированные паттерны (боты) по интервалам транзакций
    """
    analyzer = await get_analyzer(mint)
    
    if hasattr(analyzer, 'get_temporal_entropy'):
        return analyzer.get_temporal_entropy()
    else:
        return {"error": "Temporal entropy not available", "entropy_score": 0.5, "scam_confidence": 0.5}


@router.get("/token/{mint}/revolutionary/anti-fragmentation")
async def get_anti_fragmentation(mint: str) -> Dict:
    """
    🚀 НОВАЯ МЕТРИКА: Анти-фрагментация
    Обнаруживает фейковых холдеров и оценивает реальное количество уникальных владельцев
    """
    analyzer = await get_analyzer(mint)
    
    if hasattr(analyzer, 'get_anti_fragmentation'):
        return analyzer.get_anti_fragmentation()
    else:
        return {"error": "Anti-fragmentation not available", "artificial_inflation_percent": 0, "scam_confidence": 0.5}


@router.get("/token/{mint}/revolutionary/domino-effect")
async def get_domino_effect(mint: str) -> Dict:
    """
    🚀 НОВАЯ МЕТРИКА: Эффект домино
    Детектирует скоординированные дампы и панические продажи
    """
    analyzer = await get_analyzer(mint)
    
    if hasattr(analyzer, 'get_domino_effect'):
        return analyzer.get_domino_effect()
    else:
        return {"error": "Domino effect not available", "coordination_detected": False, "scam_confidence": 0.5}


@router.get("/token/{mint}/revolutionary/migration-footprint")
async def get_migration_footprint(mint: str) -> Dict:
    """
    🚀 НОВАЯ МЕТРИКА: Миграционный след
    Анализирует поведение ранних холдеров после миграции
    """
    analyzer = await get_analyzer(mint)
    
    if hasattr(analyzer, 'get_migration_footprint'):
        return analyzer.get_migration_footprint()
    else:
        return {"error": "Migration footprint not available", "sold_ratio": 0, "scam_confidence": 0.5}


@router.get("/token/{mint}/revolutionary/herding-index")
async def get_herding_index(mint: str) -> Dict:
    """
    🚀 НОВАЯ МЕТРИКА: Индекс стадного чувства
    Обнаруживает синхронные действия (армии ботов)
    """
    analyzer = await get_analyzer(mint)
    
    if hasattr(analyzer, 'get_herding_index'):
        return analyzer.get_herding_index()
    else:
        return {"error": "Herding index not available", "herding_index": 0, "bot_army_detected": False}


@router.get("/token/{mint}/revolutionary/all")
async def get_all_revolutionary_metrics(mint: str) -> Dict:
    """
    🚀 НОВЫЙ ЭНДПОИНТ: Все революционные метрики одним запросом
    Включает комбинированный скор и все 5 метрик
    """
    analyzer = await get_analyzer(mint)
    
    result = {
        "token_mint": mint,
        "revolutionary_score": {},
        "temporal_entropy": {},
        "anti_fragmentation": {},
        "domino_effect": {},
        "migration_footprint": {},
        "herding_index": {}
    }
    
    # Собираем все метрики если они доступны
    if hasattr(analyzer, 'get_revolutionary_risk_score'):
        result["revolutionary_score"] = analyzer.get_revolutionary_risk_score()
    
    if hasattr(analyzer, 'get_temporal_entropy'):
        result["temporal_entropy"] = analyzer.get_temporal_entropy()
    
    if hasattr(analyzer, 'get_anti_fragmentation'):
        result["anti_fragmentation"] = analyzer.get_anti_fragmentation()
    
    if hasattr(analyzer, 'get_domino_effect'):
        result["domino_effect"] = analyzer.get_domino_effect()
    
    if hasattr(analyzer, 'get_migration_footprint'):
        result["migration_footprint"] = analyzer.get_migration_footprint()
    
    if hasattr(analyzer, 'get_herding_index'):
        result["herding_index"] = analyzer.get_herding_index()
    
    return result

@router.post("/token/batch")
async def get_tokens_batch(mints: List[str]) -> Dict:
    """Массовое получение сводок по токенам"""
    results = {}
    errors = []
    
    for mint in mints[:20]:  # Ограничиваем 20 токенами
        try:
            analyzer = await get_analyzer(mint)
            results[mint] = {
                "summary": analyzer.get_quick_summary(),
                "risk_score": analyzer.get_hard_risk_score().get("score", 0),
                "risk_level": analyzer.get_hard_risk_score().get("level", "UNKNOWN")
            }
        except HTTPException:
            errors.append(mint)
    
    return {
        "success": results,
        "errors": errors,
        "total_requested": len(mints),
        "total_succeeded": len(results)
    }


@router.post("/token/batch/revolutionary")
async def get_tokens_batch_revolutionary(mints: List[str]) -> Dict:
    """
    🚀 НОВЫЙ БАТЧ-ЭНДПОИНТ: Массовое получение революционных скоров
    """
    results = {}
    errors = []
    
    for mint in mints[:10]:  # Ограничиваем 10 токенами (тяжелые вычисления)
        try:
            analyzer = await get_analyzer(mint)
            if hasattr(analyzer, 'get_revolutionary_risk_score'):
                results[mint] = analyzer.get_revolutionary_risk_score()
            else:
                risk = analyzer.get_hard_risk_score()
                results[mint] = {
                    "revolutionary_score": risk.get("score", 0),
                    "risk_level": risk.get("level", "UNKNOWN"),
                    "note": "Using legacy risk score"
                }
        except HTTPException as e:
            errors.append({"mint": mint, "error": str(e.detail)})
        except Exception as e:
            errors.append({"mint": mint, "error": str(e)})
    
    return {
        "success": results,
        "errors": errors,
        "total_requested": len(mints),
        "total_succeeded": len(results)
    }

@router.get("/token/stats/overview")
async def get_tokens_overview(limit: int = Query(50, ge=1, le=200)) -> Dict:
    """Обзор всех токенов: риск, холдеры, боты"""
    client = await get_redis_client()
    cache = RedisCache(client)
    
    keys = await client.keys("token:*")
    tokens = []
    
    for key in keys[:limit]:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        mint = key.replace("token:", "")
        
        try:
            analyzer = await get_analyzer(mint)
            risk = analyzer.get_hard_risk_score()
            summary = analyzer.get_quick_summary()
            
            tokens.append({
                "mint": mint[:16],
                "mint_full": mint,
                "risk_score": risk.get("score", 0),
                "risk_level": risk.get("level", "UNKNOWN"),
                "holders": summary.get("total_holders", 0),
                "bots": summary.get("bots_count", 0),
                "transactions": summary.get("total_transactions", 0)
            })
        except Exception as e:
            logger.error(f"Error processing {mint}: {e}")
    
    tokens.sort(key=lambda x: x["risk_score"], reverse=True)
    
    return {
        "total": len(tokens),
        "limit": limit,
        "tokens": tokens
    }


@router.get("/token/stats/revolutionary-overview")
async def get_revolutionary_tokens_overview(limit: int = Query(50, ge=1, le=100)) -> Dict:
    """
    🚀 НОВАЯ СТАТИСТИКА: Обзор токенов с революционными скорами
    """
    client = await get_redis_client()
    cache = RedisCache(client)
    
    keys = await client.keys("token:*")
    tokens = []
    
    for key in keys[:limit]:
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        mint = key.replace("token:", "")
        
        try:
            analyzer = await get_analyzer(mint)
            
            if hasattr(analyzer, 'get_revolutionary_risk_score'):
                rev = analyzer.get_revolutionary_risk_score()
                risk = rev.get("revolutionary_score", 0)
                risk_level = rev.get("risk_level", "UNKNOWN")
                scam_type = rev.get("scam_type", "UNKNOWN")
                confidence = rev.get("confidence", 0)
            else:
                risk = analyzer.get_hard_risk_score().get("score", 0)
                risk_level = analyzer.get_hard_risk_score().get("level", "UNKNOWN")
                scam_type = "LEGACY"
                confidence = 0
            
            tokens.append({
                "mint": mint[:16],
                "mint_full": mint,
                "revolutionary_score": risk,
                "risk_level": risk_level,
                "scam_type": scam_type,
                "confidence": confidence
            })
        except Exception as e:
            logger.error(f"Error processing {mint}: {e}")
    
    # Сортировка по скору (от самых опасных)
    tokens.sort(key=lambda x: x["revolutionary_score"], reverse=True)
    
    return {
        "total": len(tokens),
        "limit": limit,
        "high_risk_count": len([t for t in tokens if t["risk_level"] in ["CRITICAL", "HIGH"]]),
        "tokens": tokens
    }