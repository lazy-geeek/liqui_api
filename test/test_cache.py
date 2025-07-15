import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json
import asyncio
from datetime import datetime

from cache_config import (
    generate_cache_key,
    get_ttl_for_key_type,
    get_from_cache,
    set_in_cache,
    delete_from_cache,
    clear_cache_by_pattern,
    invalidate_cache_for_symbol,
    invalidate_symbols_cache,
    get_cache_stats,
    cache_result,
    CacheConfig
)


class TestCacheKeyGeneration:
    """Test suite for cache key generation."""
    
    def test_liquidations_cache_key(self):
        """Test cache key generation for liquidations."""
        key = generate_cache_key(
            "liquidations",
            symbol="BTCUSDT",
            timeframe="5m",
            start_timestamp="1609459200000",
            end_timestamp="1609462800000"
        )
        assert key == "liq:BTCUSDT:5m:1609459200000:1609462800000"
    
    def test_symbols_cache_key(self):
        """Test cache key generation for symbols."""
        key = generate_cache_key("symbols")
        assert key == "symbols:all"
    
    def test_orders_cache_key_with_limit(self):
        """Test cache key generation for orders with limit."""
        key = generate_cache_key(
            "orders",
            symbol="BTCUSDT",
            limit="100"
        )
        assert key == "orders:BTCUSDT:latest:100"
    
    def test_orders_cache_key_with_timestamps(self):
        """Test cache key generation for orders with timestamps."""
        key = generate_cache_key(
            "orders",
            symbol="BTCUSDT",
            start_timestamp="1609459200000",
            end_timestamp="1609462800000",
            page=1,
            page_size=100
        )
        assert key == "orders:BTCUSDT:1609459200000:1609462800000:page:1:size:100"
    
    def test_long_key_hashing(self):
        """Test that long keys are hashed."""
        # Create a very long key
        long_symbol = "A" * 200
        key = generate_cache_key(
            "liquidations",
            symbol=long_symbol,
            timeframe="5m",
            start_timestamp="1609459200000",
            end_timestamp="1609462800000"
        )
        assert key.startswith("liquidations:hash:")
        assert len(key) < 50  # Should be much shorter than original
    
    def test_invalid_key_type(self):
        """Test error handling for invalid key types."""
        with pytest.raises(ValueError, match="Unknown key_type"):
            generate_cache_key("invalid_type", symbol="BTCUSDT")


class TestCacheTTL:
    """Test suite for cache TTL configuration."""
    
    def test_symbols_ttl(self):
        """Test TTL for symbols cache."""
        ttl = get_ttl_for_key_type("symbols")
        assert ttl == 3600  # 1 hour
    
    def test_liquidations_ttl(self):
        """Test TTL for liquidations cache."""
        ttl = get_ttl_for_key_type("liquidations")
        assert ttl == 300  # 5 minutes
    
    def test_orders_ttl(self):
        """Test TTL for orders cache."""
        ttl = get_ttl_for_key_type("orders")
        assert ttl == 300  # 5 minutes
    
    def test_default_ttl(self):
        """Test default TTL for unknown types."""
        ttl = get_ttl_for_key_type("unknown")
        assert ttl == 300  # Default 5 minutes


class TestCacheOperations:
    """Test suite for cache operations."""
    
    @pytest.mark.asyncio
    async def test_get_from_cache_miss(self, mock_cache_unavailable):
        """Test cache miss scenario."""
        result = await get_from_cache("test_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_from_cache_hit(self, mock_cache_available):
        """Test cache hit scenario."""
        mock_redis = mock_cache_available
        test_data = {"test": "data"}
        mock_redis.get.return_value = json.dumps(test_data)
        
        result = await get_from_cache("test_key")
        assert result == test_data
        mock_redis.get.assert_called_once_with("test_key")
    
    @pytest.mark.asyncio
    async def test_get_from_cache_error(self, mock_cache_available):
        """Test cache get error handling."""
        mock_redis = mock_cache_available
        mock_redis.get.side_effect = Exception("Redis error")
        
        result = await get_from_cache("test_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_in_cache_success(self, mock_cache_available):
        """Test successful cache set."""
        mock_redis = mock_cache_available
        test_data = {"test": "data"}
        
        result = await set_in_cache("test_key", test_data, 300)
        assert result is True
        mock_redis.setex.assert_called_once_with("test_key", 300, json.dumps(test_data, default=str))
    
    @pytest.mark.asyncio
    async def test_set_in_cache_unavailable(self, mock_cache_unavailable):
        """Test cache set when cache is unavailable."""
        result = await set_in_cache("test_key", {"test": "data"}, 300)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_set_in_cache_error(self, mock_cache_available):
        """Test cache set error handling."""
        mock_redis = mock_cache_available
        mock_redis.setex.side_effect = Exception("Redis error")
        
        result = await set_in_cache("test_key", {"test": "data"}, 300)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_from_cache_success(self, mock_cache_available):
        """Test successful cache delete."""
        mock_redis = mock_cache_available
        
        result = await delete_from_cache("test_key")
        assert result is True
        mock_redis.delete.assert_called_once_with("test_key")
    
    @pytest.mark.asyncio
    async def test_clear_cache_by_pattern(self, mock_cache_available):
        """Test clearing cache by pattern."""
        mock_redis = mock_cache_available
        mock_redis.keys.return_value = ["key1", "key2", "key3"]
        
        result = await clear_cache_by_pattern("test:*")
        assert result == 3
        mock_redis.keys.assert_called_once_with("test:*")
        mock_redis.delete.assert_called_once_with("key1", "key2", "key3")
    
    @pytest.mark.asyncio
    async def test_clear_cache_by_pattern_no_keys(self, mock_cache_available):
        """Test clearing cache by pattern with no matching keys."""
        mock_redis = mock_cache_available
        mock_redis.keys.return_value = []
        
        result = await clear_cache_by_pattern("test:*")
        assert result == 0
        mock_redis.keys.assert_called_once_with("test:*")
        mock_redis.delete.assert_not_called()


class TestCacheInvalidation:
    """Test suite for cache invalidation."""
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_for_symbol(self, mock_cache_available):
        """Test invalidating cache for a specific symbol."""
        mock_redis = mock_cache_available
        
        # Mock different numbers of keys for different patterns
        def mock_keys_side_effect(pattern):
            if pattern == "liq:BTCUSDT:*":
                return ["liq:BTCUSDT:5m:123:456", "liq:BTCUSDT:1h:789:012"]
            elif pattern == "orders:BTCUSDT:*":
                return ["orders:BTCUSDT:latest:100"]
            return []
        
        mock_redis.keys.side_effect = mock_keys_side_effect
        
        with patch('cache_config.clear_cache_by_pattern') as mock_clear:
            mock_clear.side_effect = [2, 1]  # Return different counts for each pattern
            
            result = await invalidate_cache_for_symbol("BTCUSDT")
            assert result == 3  # Total of 2 + 1
            
            # Verify both patterns were cleared
            from unittest.mock import call
            mock_clear.assert_has_calls([
                call("liq:BTCUSDT:*"),
                call("orders:BTCUSDT:*")
            ])
    
    @pytest.mark.asyncio
    async def test_invalidate_symbols_cache(self, mock_cache_available):
        """Test invalidating symbols cache."""
        with patch('cache_config.delete_from_cache') as mock_delete:
            mock_delete.return_value = True
            
            result = await invalidate_symbols_cache()
            assert result is True
            mock_delete.assert_called_once_with("symbols:all")


class TestCacheStats:
    """Test suite for cache statistics."""
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_available(self, mock_cache_available):
        """Test getting cache stats when cache is available."""
        mock_redis = mock_cache_available
        
        result = await get_cache_stats()
        
        assert result["available"] is True
        assert result["connected_clients"] == 1
        assert result["used_memory"] == 1024
        assert result["used_memory_human"] == "1K"
        assert result["keyspace_hits"] == 100
        assert result["keyspace_misses"] == 50
        assert result["total_commands_processed"] == 1000
        assert result["hit_rate"] == 66.67  # 100/(100+50) * 100
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_unavailable(self, mock_cache_unavailable):
        """Test getting cache stats when cache is unavailable."""
        result = await get_cache_stats()
        
        assert result["available"] is False
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_error(self, mock_cache_available):
        """Test getting cache stats with Redis error."""
        mock_redis = mock_cache_available
        mock_redis.info.side_effect = Exception("Redis error")
        
        result = await get_cache_stats()
        
        assert result["available"] is False
        assert result["error"] == "Redis error"
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_zero_requests(self, mock_cache_available):
        """Test cache stats with zero requests (hit rate calculation)."""
        mock_redis = mock_cache_available
        mock_redis.info.return_value = {
            'keyspace_hits': 0,
            'keyspace_misses': 0,
            'connected_clients': 1,
            'used_memory': 1024,
            'used_memory_human': '1K',
            'total_commands_processed': 0
        }
        
        result = await get_cache_stats()
        
        assert result["hit_rate"] == 0


class TestCacheDecorator:
    """Test suite for cache result decorator."""
    
    @pytest.mark.asyncio
    async def test_cache_decorator_miss(self, mock_cache_available):
        """Test cache decorator with cache miss."""
        mock_redis = mock_cache_available
        mock_redis.get.return_value = None  # Cache miss
        
        @cache_result("liquidations")
        async def test_function(symbol="BTCUSDT", timeframe="5m", start_timestamp="123", end_timestamp="456"):
            return {"test": "data"}
        
        with patch('cache_config.get_from_cache', return_value=None) as mock_get:
            with patch('cache_config.set_in_cache', return_value=True) as mock_set:
                result = await test_function()
                
                assert result == {"test": "data"}
                mock_get.assert_called_once()
                mock_set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_decorator_hit(self, mock_cache_available):
        """Test cache decorator with cache hit."""
        cached_data = {"cached": "data"}
        
        @cache_result("liquidations")
        async def test_function(symbol="BTCUSDT", timeframe="5m", start_timestamp="123", end_timestamp="456"):
            return {"test": "data"}
        
        with patch('cache_config.get_from_cache', return_value=cached_data) as mock_get:
            with patch('cache_config.set_in_cache') as mock_set:
                result = await test_function()
                
                assert result == cached_data
                mock_get.assert_called_once()
                mock_set.assert_not_called()  # Should not set on cache hit


class TestCacheConfig:
    """Test suite for CacheConfig class."""
    
    @pytest.mark.asyncio
    async def test_cache_config_initialization(self):
        """Test CacheConfig initialization."""
        cache = CacheConfig()
        assert cache.redis_client is None
        assert cache.is_available is False
    
    @pytest.mark.asyncio
    async def test_cache_config_successful_initialization(self):
        """Test successful cache initialization."""
        cache = CacheConfig()
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis_instance = AsyncMock()
            mock_redis_class.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            
            await cache.initialize()
            
            assert cache.is_available is True
            assert cache.redis_client is not None
            mock_redis_instance.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_config_failed_initialization(self):
        """Test failed cache initialization."""
        cache = CacheConfig()
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis_instance = AsyncMock()
            mock_redis_class.return_value = mock_redis_instance
            mock_redis_instance.ping.side_effect = Exception("Connection failed")
            
            await cache.initialize()
            
            assert cache.is_available is False
            assert cache.redis_client is None
    
    @pytest.mark.asyncio
    async def test_cache_config_close(self):
        """Test cache configuration cleanup."""
        cache = CacheConfig()
        
        # Mock an initialized cache
        mock_redis = AsyncMock()
        cache.redis_client = mock_redis
        cache.is_available = True
        
        with patch('cache_config._redis_client', mock_redis):
            await cache.close()
            
            assert cache.is_available is False
            mock_redis.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_client_lazy_initialization(self):
        """Test lazy initialization when getting client."""
        cache = CacheConfig()
        
        with patch.object(cache, 'initialize') as mock_init:
            mock_init.return_value = None
            cache.is_available = True
            cache.redis_client = AsyncMock()
            
            client = await cache.get_client()
            
            assert client is not None
            mock_init.assert_called_once()