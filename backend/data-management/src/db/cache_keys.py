class CacheKeys:
    TOKEN_PREFIX = "token:"
    META_PREFIX = "meta:"
    TOKEN_METRICS_PREFIX = "token:metrics:"
    TOKEN_CHART_PREFIX = "token:chart:"
    
    TOP_TOKENS_BY_RISK = "top:tokens:risk"
    TOP_TOKENS_BY_VOLUME = "top:tokens:volume"
    TOP_TOKENS_BY_HOLDERS = "top:tokens:holders"
    
    ANALYSIS_QUEUE = "queue:analysis"
    UPDATE_QUEUE = "queue:updates"
    
    DAILY_METRICS = "metrics:daily"
    HOURLY_METRICS = "metrics:hourly"
    
    SYSTEM_HEALTH = "system:health"
    LAST_COLLECTION_TIME = "system:last_collection"
    
    @staticmethod
    def token_key(mint: str) -> str:
        return f"{CacheKeys.TOKEN_PREFIX}{mint}"
    
    @staticmethod
    def meta_key(mint: str) -> str:
        return f"{CacheKeys.META_PREFIX}{mint}"
    
    @staticmethod
    def token_metrics_key(mint: str) -> str:
        return f"{CacheKeys.TOKEN_METRICS_PREFIX}{mint}"
    
    @staticmethod
    def token_chart_key(mint: str) -> str:
        return f"{CacheKeys.TOKEN_CHART_PREFIX}{mint}"
    
    @staticmethod
    def daily_metrics_key(date: str) -> str:
        return f"{CacheKeys.DAILY_METRICS}:{date}"
    
    @staticmethod
    def hourly_metrics_key(date: str, hour: int) -> str:
        return f"{CacheKeys.HOURLY_METRICS}:{date}:{hour:02d}"


class CacheTTL:
    TOKEN_DATA = 86400
    TOKEN_METRICS = 3600
    CHART_DATA = 86400
    TOP_LISTS = 3600
    QUEUE_MESSAGE = 604800
    DAILY_METRICS = 604800
    HOURLY_METRICS = 86400
    SYSTEM_HEALTH = 60
    LOCK_TIMEOUT = 30


class CacheLimits:
    MAX_CHART_POINTS = 500
    MAX_TOP_TOKENS = 100
    MAX_QUEUE_SIZE = 10000
    BATCH_SIZE = 100