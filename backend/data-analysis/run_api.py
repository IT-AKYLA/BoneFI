import uvicorn
import os
import sys
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

def signal_handler(sig, frame):
    print("\nReceived shutdown signal, exiting...")
    sys.exit(0)

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "8000"))
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        workers=1,
        timeout_keep_alive=65,
        timeout_graceful_shutdown=10,
        limit_concurrency=10,
        limit_max_requests=1000
    )