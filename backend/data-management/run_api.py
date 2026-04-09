import uvicorn
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "8001"))
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,      
        workers=1,
        loop="asyncio",
        timeout_keep_alive=5,
        log_level="info"
    )