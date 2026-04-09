# data-analysis/src/services/scheduler.py
import asyncio
import logging
from datetime import datetime
from typing import List, Set
import os

from ..core.database import RedisCache, get_redis_client
from ..services.analyzer import TokenAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TokenScheduler:
    """Автоматический планировщик анализа токенов"""
    
    def __init__(self):
        self._is_scanning = False
        self.cache = None
        self.client = None
        self.running = False
        self.analyzed_tokens: Set[str] = set()
        self.last_scan_time = None
        self.scan_interval = int(os.getenv("SCAN_INTERVAL_MINUTES", "30"))
        self.batch_size = int(os.getenv("BATCH_SIZE_HISTORY", "5"))
        
    async def initialize(self):
        if self.client is not None:
            return
        
        self.client = await get_redis_client()
        self.cache = RedisCache(self.client)
        await self.load_analyzed_tokens()
        
    async def load_analyzed_tokens(self):
        try:
            keys = await self.client.keys("history:*")
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                mint = key.replace("history:", "")
                self.analyzed_tokens.add(mint)
            logger.info(f"📚 Loaded {len(self.analyzed_tokens)} already analyzed tokens from history")
        except Exception as e:
            logger.error(f"Error loading analyzed tokens: {e}")
    
    async def get_all_tokens_in_redis(self) -> List[str]:
        try:
            keys = await self.client.keys("token:*")
            tokens = []
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                mint = key.replace("token:", "")
                tokens.append(mint)
            return tokens
        except Exception as e:
            logger.error(f"Error getting tokens from Redis: {e}")
            return []
    
    async def analyze_token(self, mint: str, force: bool = False) -> bool:
        """Анализирует токен в отдельном потоке"""
        try:
            if not force:
                existing_history = await self.cache.get_analysis_history(mint)
                if existing_history:
                    logger.debug(f"Token {mint[:16]}... already in history, skipping")
                    return False
            
            data = await self.cache.get_token(mint)
            if not data:
                logger.warning(f"No data for token {mint}")
                return False
            
            # Выносим анализ в отдельный поток, чтобы не блокировать event loop
            def run_analysis():
                analyzer = TokenAnalyzer(data)
                return analyzer.get_full_analysis(save_history=True)
            
            # Таймаут 120 секунд на анализ
            analysis_result = await asyncio.wait_for(
                asyncio.to_thread(run_analysis),
                timeout=120.0
            )
            
            await self.cache.save_analysis_history(mint, analysis_result)
            
            risk_score = analysis_result.get("risk_assessment", {}).get("score", 0)
            await self.cache.add_to_daily_analytics(mint, risk_score)
            
            self.analyzed_tokens.add(mint)
            logger.info(f"Analyzed: {mint[:16]}... (Risk: {risk_score})")
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout analyzing {mint[:16]}... (>120 seconds)")
            return False
        except Exception as e:
            logger.error(f"Error analyzing token {mint}: {e}")
            return False
    
    async def scan_and_analyze(self, force_reanalyze: bool = False):
        self._is_scanning = True
        try:
            await self.initialize()

            logger.info("🔍 Starting scan for tokens...")

            all_tokens = await self.get_all_tokens_in_redis()
            logger.info(f"📊 Found {len(all_tokens)} total tokens in Redis")

            if force_reanalyze:
                tokens_to_process = all_tokens
            else:
                tokens_to_process = [t for t in all_tokens if t not in self.analyzed_tokens]

            logger.info(f"🆕 Found {len(tokens_to_process)} new tokens to analyze")

            if not tokens_to_process:
                logger.info("✅ No new tokens to process")
                self.last_scan_time = datetime.now()
                return

            tokens_batch = tokens_to_process[:self.batch_size]
            logger.info(f"📦 Processing batch of {len(tokens_batch)} tokens")

            success_count = 0
            for mint in tokens_batch:
                if not self.running:
                    break
                
                logger.info(f"🔍 Analyzing: {mint[:16]}...")
                
                if await self.analyze_token(mint, force=force_reanalyze):
                    success_count += 1
                
                await asyncio.sleep(0.5)

            logger.info(f"✅ Scan complete. Analyzed: {success_count}/{len(tokens_batch)}")
            self.last_scan_time = datetime.now()
            
        except Exception as e:
            logger.error(f"Error in scan: {e}")
        finally:
            self._is_scanning = False
    
    async def reanalyze_token(self, mint: str) -> bool:
        await self.initialize()
        logger.info(f"🔄 Force reanalyzing token: {mint[:16]}...")
        return await self.analyze_token(mint, force=True)
    
    async def run_forever(self):
        if self.running:
            return
        
        await self.initialize()
        self.running = True
        
        logger.info(f"🔄 Scheduler started. Scan interval: {self.scan_interval} minutes")
        
        while self.running:
            try:
                await self.scan_and_analyze(force_reanalyze=False)
                
                if self.running:
                    logger.info(f"⏳ Waiting {self.scan_interval} minutes until next scan...")
                    for _ in range(self.scan_interval * 60):
                        if not self.running:
                            break
                        await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info("Scan cancelled")
                break
            except Exception as e:
                logger.error(f"Error in scan loop: {e}")
                if self.running:
                    await asyncio.sleep(60)
        
        logger.info("Scheduler stopped")
    
    def stop(self):
        self.running = False
        logger.info("Scheduler stop requested")


scheduler = TokenScheduler()