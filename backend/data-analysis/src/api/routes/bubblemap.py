from fastapi import APIRouter, HTTPException
from typing import Dict, List
from ...core.database import RedisCache, get_redis_client
from ...services.analyzer import TokenAnalyzer
from ...services import clean_numpy

router = APIRouter()


@router.get("/bubblemap/{mint}")
async def get_bubblemap_data(mint: str) -> Dict:
    client = await get_redis_client()
    cache = RedisCache(client)
    
    data = await cache.get_token(mint)
    
    if not data:
        raise HTTPException(status_code=404, detail="Token not found")
    
    analyzer = TokenAnalyzer(data)
    analyzer._ensure_initialized()

    total_balance = sum(analyzer.current_holders.values())
    
    # Защита от пустых данных
    if total_balance == 0:
        result = {
            "token_mint": mint,
            "total_holders": 0,
            "total_supply_millions": 0,
            "holders": [],
            "stats": {
                "whale_count": 0,
                "large_count": 0,
                "bot_count": 0,
                "bot_share": 0,
                "visible_bot_count": 0,
                "insider_count": 0,
                "insider_share": 0,
                "visible_insider_count": 0,
                "suspicious_count": 0,
                "suspicious_share": 0,
                "filtered_count": 0,
                "filtered_percent": 0
            }
        }
        result = clean_numpy(result)
        return result
    
    # Получаем ВСЕХ подозрительных из SSI
    suspicious_supply = analyzer.calculate_suspicious_supply_index()
    
    # Создаём множества
    suspicious_addresses = set()
    insider_addresses = set()
    bot_addresses = set()
    
    if "categories" in suspicious_supply:
        for addr in suspicious_supply["categories"].get("insider_snipers", {}).get("wallets", []):
            suspicious_addresses.add(addr)
            insider_addresses.add(addr)
        
        for addr in suspicious_supply["categories"].get("cluster_bots", {}).get("wallets", []):
            suspicious_addresses.add(addr)
            bot_addresses.add(addr)
        
        for addr in suspicious_supply["categories"].get("rapid_sellers", {}).get("wallets", []):
            suspicious_addresses.add(addr)
            bot_addresses.add(addr)
    
    # Собираем всех холдеров
    all_holders = []
    for addr, balance in analyzer.current_holders.items():
        share = (balance / total_balance * 100) if total_balance > 0 else 0
        tx_count = analyzer.address_activity.get(addr, 0)
        is_pool = analyzer.is_liquidity_pool(addr, share, tx_count)
        is_bot = addr in bot_addresses
        is_insider = addr in insider_addresses
        is_suspicious = addr in suspicious_addresses
        
        all_holders.append({
            "id": addr[:8],
            "address": addr,
            "share": float(round(share, 6)),  # явно в float
            "balance": float(balance / (10 ** analyzer.decimals)),  # явно в float
            "tx_count": int(tx_count),  # явно в int
            "is_pool": bool(is_pool),
            "is_bot": bool(is_bot),
            "is_insider": bool(is_insider),
            "is_suspicious": bool(is_suspicious)
        })
    
    # ФИЛЬТРУЕМ для отображения на карте
    MIN_SHARE_FOR_DISPLAY = 0.1
    
    filtered_holders = [
        h for h in all_holders 
        if h["is_pool"] or (h["share"] >= MIN_SHARE_FOR_DISPLAY)
    ]
    
    filtered_holders.sort(key=lambda x: x["share"], reverse=True)
    
    # Статистика для отображения
    bot_holders = [h for h in all_holders if h["is_bot"]]
    insider_holders = [h for h in all_holders if h["is_insider"]]
    suspicious_holders = [h for h in all_holders if h["is_suspicious"]]
    
    visible_bots = [h for h in filtered_holders if h["is_bot"]]
    visible_insiders = [h for h in filtered_holders if h["is_insider"]]
    
    bot_total_share = sum(h["share"] for h in bot_holders)
    insider_total_share = sum(h["share"] for h in insider_holders)
    
    result = {
        "token_mint": mint,
        "total_holders": len(all_holders),
        "total_supply_millions": float(analyzer.total_supply_formatted / 1_000_000),
        "holders": filtered_holders,
        "stats": {
            "whale_count": int(len([h for h in all_holders if h["share"] > 5 and not h["is_pool"]])),
            "large_count": int(len([h for h in all_holders if 1 < h["share"] <= 5 and not h["is_pool"]])),
            "bot_count": len(bot_holders),
            "bot_share": float(round(bot_total_share, 2)),
            "visible_bot_count": len(visible_bots),
            "insider_count": len(insider_holders),
            "insider_share": float(round(insider_total_share, 2)),
            "visible_insider_count": len(visible_insiders),
            "suspicious_count": len(suspicious_holders),
            "suspicious_share": float(round(suspicious_supply.get("suspicious_supply_percent", 0), 1)),
            "filtered_count": len(filtered_holders),
            "filtered_percent": float(round(len(filtered_holders) / len(all_holders) * 100, 1)) if all_holders else 0
        }
    }
    
    result = clean_numpy(result)
    
    return result