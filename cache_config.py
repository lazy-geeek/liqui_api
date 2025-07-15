import redis.asyncio as redis
import os
import json
import hashlib
from typing import Optional, Any, Dict
from datetime import datetime
from urllib.parse import urlparse


# Redis configuration from environment variables
# Support both individual vars and Dokku's REDIS_URL
def get_redis_config():
    """Get Redis configuration from environment variables."""
    redis_url = os.getenv("REDIS_URL")
    
    if redis_url:
        # Parse Dokku's REDIS_URL format: redis://[:password@]host[:port][/db]
        parsed = urlparse(redis_url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 6379,
            "password": parsed.password,
            "db": int(parsed.path.lstrip("/") or "0"),
            "decode_responses": True,
        }
    else:
        # Fallback to individual environment variables
        return {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6379")),
            "password": os.getenv("REDIS_PASSWORD") or None,
            "db": int(os.getenv("REDIS_DB", "0")),
            "decode_responses": True,
        }

REDIS_CONFIG = get_redis_config()

# Cache TTL configuration
DEFAULT_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes
SYMBOLS_TTL = int(os.getenv("CACHE_TTL_SYMBOLS", "3600"))  # 1 hour

# Global Redis client
_redis_client: Optional[redis.Redis] = None


class CacheConfig:
    """Redis cache configuration and management."""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.is_available = False
    
    async def initialize(self) -> None:
        """Initialize Redis connection."""
        global _redis_client
        try:
            _redis_client = redis.Redis(**REDIS_CONFIG)
            # Test connection
            await _redis_client.ping()
            self.redis_client = _redis_client
            self.is_available = True
            print("INFO: Redis cache initialized successfully")
        except Exception as e:
            print(f"WARNING: Redis connection failed: {e}")
            print("INFO: Continuing without cache - all requests will go to database")
            self.is_available = False
    
    async def close(self) -> None:
        """Close Redis connection."""
        global _redis_client
        if _redis_client:
            await _redis_client.close()
            _redis_client = None
            self.is_available = False
            print("INFO: Redis cache connection closed")
    
    async def get_client(self) -> Optional[redis.Redis]:
        """Get Redis client, initializing if necessary."""
        if not self.is_available:
            await self.initialize()
        return self.redis_client if self.is_available else None


# Global cache instance
cache = CacheConfig()


# ==================== Cache Key Generation ====================

def generate_cache_key(key_type: str, **kwargs) -> str:
    """
    Generate standardized cache keys.
    
    Args:
        key_type: Type of cache key (liquidations, symbols, orders)
        **kwargs: Parameters to include in the key
    
    Returns:
        Standardized cache key string
    """
    if key_type == "liquidations":
        symbol = kwargs.get("symbol", "")
        timeframe = kwargs.get("timeframe", "")
        start = kwargs.get("start_timestamp", "")
        end = kwargs.get("end_timestamp", "")
        base_key = f"liq:{symbol}:{timeframe}:{start}:{end}"
    elif key_type == "symbols":
        base_key = "symbols:all"
    elif key_type == "orders":
        symbol = kwargs.get("symbol", "")
        start = kwargs.get("start_timestamp", "")
        end = kwargs.get("end_timestamp", "")
        limit = kwargs.get("limit", "")
        page = kwargs.get("page", 1)
        page_size = kwargs.get("page_size", 100)
        if limit:
            base_key = f"orders:{symbol}:latest:{limit}"
        else:
            base_key = f"orders:{symbol}:{start}:{end}:page:{page}:size:{page_size}"
    else:
        raise ValueError(f"Unknown key_type: {key_type}")
    
    # Hash long keys to avoid Redis key length limits
    if len(base_key) > 200:
        hash_obj = hashlib.sha256(base_key.encode())
        return f"{key_type}:hash:{hash_obj.hexdigest()[:16]}"
    
    return base_key


def get_ttl_for_key_type(key_type: str) -> int:
    """
    Get TTL based on key type.
    
    Args:
        key_type: Type of cache key
    
    Returns:
        TTL in seconds
    """
    if key_type == "symbols":
        return SYMBOLS_TTL
    elif key_type in ["liquidations", "orders"]:
        return DEFAULT_TTL
    else:
        return DEFAULT_TTL


# ==================== Cache Operations ====================

async def get_from_cache(key: str) -> Optional[Any]:
    """
    Get value from cache.
    
    Args:
        key: Cache key
    
    Returns:
        Cached value or None if not found/cache unavailable
    """
    client = await cache.get_client()
    if not client:
        return None
    
    try:
        cached_value = await client.get(key)
        if cached_value:
            return json.loads(cached_value)
    except Exception as e:
        print(f"WARNING: Cache get error for key '{key}': {e}")
    
    return None


async def set_in_cache(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Set value in cache.
    
    Args:
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds
    
    Returns:
        True if set successfully, False otherwise
    """
    client = await cache.get_client()
    if not client:
        return False
    
    try:
        serialized_value = json.dumps(value, default=str)
        await client.setex(key, ttl, serialized_value)
        return True
    except Exception as e:
        print(f"WARNING: Cache set error for key '{key}': {e}")
        return False


async def delete_from_cache(key: str) -> bool:
    """
    Delete value from cache.
    
    Args:
        key: Cache key
    
    Returns:
        True if deleted successfully, False otherwise
    """
    client = await cache.get_client()
    if not client:
        return False
    
    try:
        await client.delete(key)
        return True
    except Exception as e:
        print(f"WARNING: Cache delete error for key '{key}': {e}")
        return False


async def clear_cache_by_pattern(pattern: str) -> int:
    """
    Clear cache keys matching a pattern.
    
    Args:
        pattern: Redis pattern (e.g., "liq:*", "symbols:*")
    
    Returns:
        Number of keys deleted
    """
    client = await cache.get_client()
    if not client:
        return 0
    
    try:
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
            return len(keys)
        return 0
    except Exception as e:
        print(f"WARNING: Cache clear error for pattern '{pattern}': {e}")
        return 0


# ==================== Cache Decorator ====================

def cache_result(key_type: str, ttl: Optional[int] = None):
    """
    Decorator to cache function results.
    
    Args:
        key_type: Type of cache key
        ttl: Time to live in seconds (optional)
    
    Returns:
        Decorator function
    """
    def decorator(func):
        from functools import wraps
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function arguments
            cache_key = generate_cache_key(key_type, **kwargs)
            
            # Try to get from cache first
            cached_result = await get_from_cache(cache_key)
            if cached_result is not None:
                print(f"INFO: Cache hit for key: {cache_key}")
                return cached_result
            
            # Cache miss - execute function
            print(f"INFO: Cache miss for key: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Cache the result
            cache_ttl = ttl if ttl is not None else get_ttl_for_key_type(key_type)
            await set_in_cache(cache_key, result, cache_ttl)
            
            return result
        return wrapper
    return decorator


# ==================== Cache Invalidation ====================

async def invalidate_cache_for_symbol(symbol: str) -> int:
    """
    Invalidate all cache entries for a specific symbol.
    
    Args:
        symbol: Trading symbol
    
    Returns:
        Number of keys invalidated
    """
    patterns = [
        f"liq:{symbol}:*",
        f"orders:{symbol}:*",
    ]
    
    total_deleted = 0
    for pattern in patterns:
        deleted = await clear_cache_by_pattern(pattern)
        total_deleted += deleted
    
    return total_deleted


async def invalidate_symbols_cache() -> bool:
    """
    Invalidate the symbols cache.
    
    Returns:
        True if invalidated successfully
    """
    return await delete_from_cache("symbols:all")


# ==================== Cache Statistics ====================

async def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.
    
    Returns:
        Dictionary with cache statistics
    """
    client = await cache.get_client()
    if not client:
        return {"available": False, "error": "Cache not available"}
    
    try:
        info = await client.info()
        stats = {
            "available": True,
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
        }
        
        # Calculate hit rate
        hits = stats["keyspace_hits"]
        misses = stats["keyspace_misses"]
        total = hits + misses
        if total > 0:
            stats["hit_rate"] = round((hits / total) * 100, 2)
        else:
            stats["hit_rate"] = 0
        
        return stats
    except Exception as e:
        return {"available": False, "error": str(e)}


# ==================== Application Lifecycle Events ====================

async def cache_startup_event():
    """FastAPI startup event handler for cache initialization."""
    await cache.initialize()


async def cache_shutdown_event():
    """FastAPI shutdown event handler for cache cleanup."""
    await cache.close()


# ==================== Cache Warming ====================

async def warm_cache_popular_symbols():
    """
    Warm cache with popular symbols.
    This should be called during startup or periodically.
    """
    try:
        # Import here to avoid circular imports
        from app_async_db import async_execute_query
        import os
        
        table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
        
        # Get symbols cache first
        query = f"""
        SELECT DISTINCT symbol
        FROM {table_name}
        WHERE symbol NOT REGEXP '[0-9]+$'
        ORDER BY symbol
        """
        
        symbols_result = await async_execute_query(query, ())
        if symbols_result:
            symbols = [result[0] for result in symbols_result]
            # Cache the symbols list
            await set_in_cache("symbols:all", symbols, SYMBOLS_TTL)
            print(f"INFO: Warmed symbols cache with {len(symbols)} symbols")
        
        return True
    except Exception as e:
        print(f"WARNING: Cache warming for symbols failed: {e}")
        return False


async def warm_cache_popular_liquidations():
    """
    Warm cache with popular liquidation queries.
    Focuses on major trading pairs and common timeframes.
    """
    try:
        # Import here to avoid circular imports
        from app_async_db import async_execute_query
        import os
        from datetime import datetime, timedelta
        
        table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
        
        # Popular symbols to warm
        popular_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT", "XRPUSDT"]
        # Popular timeframes
        popular_timeframes = ["5m", "15m", "1h", "4h", "1d"]
        
        # Get recent time range (last 24 hours)
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        start_timestamp_ms = int(start_time.timestamp() * 1000)
        end_timestamp_ms = int(end_time.timestamp() * 1000)
        
        warmed_count = 0
        
        for symbol in popular_symbols:
            for timeframe in popular_timeframes:
                try:
                    # Generate cache key
                    cache_key = generate_cache_key(
                        "liquidations",
                        symbol=symbol,
                        timeframe=timeframe,
                        start_timestamp=start_timestamp_ms,
                        end_timestamp=end_timestamp_ms
                    )
                    
                    # Check if already cached
                    cached = await get_from_cache(cache_key)
                    if cached is not None:
                        continue
                    
                    # Convert timeframe to milliseconds (simplified version)
                    timeframe_ms = convert_timeframe_to_milliseconds(timeframe)
                    
                    # Execute liquidations query
                    query = f"""
                    SELECT symbol,
                           FLOOR((order_trade_time - %s) / %s) * %s + %s AS start_timestamp,
                           FLOOR((order_trade_time - %s) / %s) * %s + %s + %s AS end_timestamp,
                           side,
                           SUM(average_price * order_filled_accumulated_quantity) AS cumulated_usd_size
                    FROM {table_name}
                    WHERE LOWER(symbol) = %s
                      AND order_trade_time BETWEEN %s AND %s
                    GROUP BY symbol, start_timestamp, end_timestamp, side;
                    """
                    
                    params = (
                        start_timestamp_ms, timeframe_ms, timeframe_ms, start_timestamp_ms,
                        start_timestamp_ms, timeframe_ms, timeframe_ms, start_timestamp_ms, timeframe_ms,
                        symbol.lower(), start_timestamp_ms, end_timestamp_ms,
                    )
                    
                    db_results = await async_execute_query(query, params)
                    
                    if db_results:
                        # Format results like the API endpoint
                        results = [
                            {
                                "timestamp": result[1],
                                "timestamp_iso": datetime.fromtimestamp(
                                    int(result[1]) / 1000
                                ).isoformat() + "Z",
                                "side": result[3],
                                "cumulated_usd_size": float(result[4]),
                            }
                            for result in db_results
                        ]
                        
                        # Cache the results
                        await set_in_cache(cache_key, results, DEFAULT_TTL)
                        warmed_count += 1
                
                except Exception as e:
                    print(f"WARNING: Failed to warm cache for {symbol} {timeframe}: {e}")
                    continue
        
        print(f"INFO: Warmed liquidations cache with {warmed_count} popular queries")
        return True
        
    except Exception as e:
        print(f"WARNING: Cache warming for liquidations failed: {e}")
        return False


def convert_timeframe_to_milliseconds(timeframe: str) -> int:
    """
    Convert timeframe string to milliseconds.
    Simplified version for cache warming.
    """
    if timeframe.endswith('m'):
        return int(timeframe[:-1]) * 60 * 1000
    elif timeframe.endswith('h'):
        return int(timeframe[:-1]) * 60 * 60 * 1000
    elif timeframe.endswith('d'):
        return int(timeframe[:-1]) * 24 * 60 * 60 * 1000
    else:
        raise ValueError(f"Invalid timeframe: {timeframe}")


async def warm_all_caches():
    """
    Warm all caches - symbols and popular liquidations.
    This should be called during startup.
    """
    print("INFO: Starting cache warming...")
    
    # Warm symbols cache
    symbols_success = await warm_cache_popular_symbols()
    
    # Warm popular liquidations cache
    liquidations_success = await warm_cache_popular_liquidations()
    
    if symbols_success and liquidations_success:
        print("INFO: Cache warming completed successfully")
    elif symbols_success or liquidations_success:
        print("INFO: Cache warming partially completed")
    else:
        print("WARNING: Cache warming failed")


# ==================== Circuit Breaker (Future Enhancement) ====================

class CacheCircuitBreaker:
    """
    Circuit breaker for cache operations.
    This prevents cascading failures when Redis is down.
    """
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    async def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.
        """
        if self.state == "open":
            if datetime.now().timestamp() - self.last_failure_time > self.timeout:
                self.state = "half-open"
            else:
                return None
        
        try:
            result = await func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now().timestamp()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            
            print(f"WARNING: Circuit breaker triggered: {e}")
            return None


# Global circuit breaker instance
circuit_breaker = CacheCircuitBreaker()