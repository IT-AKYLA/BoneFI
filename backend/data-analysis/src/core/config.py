import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
    REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
    REDIS_SOCKET_CONNECT_TIMEOUT = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))
    # ВАЖНО: decode_responses=False для бинарных данных
    REDIS_DECODE_RESPONSES = os.getenv("REDIS_DECODE_RESPONSES", "false").lower() == "true"
    
    # Rate Limit
    RATE_LIMIT_DEFAULT = int(os.getenv("RATE_LIMIT_DEFAULT", "30"))
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    
    # API
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))


config = Config()