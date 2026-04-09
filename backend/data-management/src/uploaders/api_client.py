import aiohttp
import asyncio
import os
from typing import Dict, Optional

API_URL = os.getenv("API_URL", "https://your-api.up.railway.app")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))


class APIClient:
    def __init__(self):
        self.base_url = API_URL.rstrip('/')
        self.timeout = API_TIMEOUT
        self.max_retries = MAX_RETRIES

    async def send_analysis(self, token_mint: str, analysis_data: Dict) -> bool:
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "token_mint": token_mint,
                        "analysis_data": analysis_data,
                        "timestamp": analysis_data.get("collected_at")
                    }
                    
                    async with session.post(
                        f"{self.base_url}/webhook/new-data",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                    ) as resp:
                        if resp.status == 200:
                            return True
                        else:
                            error_text = await resp.text()
                            print(f"API error (attempt {attempt + 1}): {resp.status} - {error_text}")
                            
            except asyncio.TimeoutError:
                print(f"API timeout (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                print(f"API exception (attempt {attempt + 1}): {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return False

    async def send_batch(self, analyses: Dict[str, Dict]) -> Dict[str, bool]:
        results = {}
        for mint, data in analyses.items():
            results[mint] = await self.send_analysis(mint, data)
            await asyncio.sleep(0.1)
        return results

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False