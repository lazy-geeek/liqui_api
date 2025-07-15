import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock
import mysql.connector
import asyncio
from app import app


class TestIntegration:
    """Integration tests for the API endpoints."""
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    @patch('cache_config.get_from_cache')
    @patch('cache_config.set_in_cache')
    async def test_complete_liquidations_flow(self, mock_set_cache, mock_get_cache, mock_execute_query, mock_env_vars):
        """Test complete request/response cycle for liquidations endpoint."""
        # Mock cache miss
        mock_get_cache.return_value = None
        mock_set_cache.return_value = True
        
        # Mock database query
        mock_execute_query.return_value = [
            ('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5),
            ('BTCUSDT', 1609459200000, 1609459500000, 'sell', 200.75),
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Make request
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "5m",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(isinstance(item["cumulated_usd_size"], float) for item in data)
        
        # Verify cache integration
        mock_get_cache.assert_called_once()
        mock_set_cache.assert_called_once()
        mock_execute_query.assert_called_once()


class TestAsyncDatabaseIntegration:
    """Integration tests for async database operations."""
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_async_database_connection_pool(self, mock_execute_query, mock_env_vars):
        """Test async database connection pool integration."""
        mock_execute_query.return_value = [('BTCUSDT',), ('ETHUSDT',)]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Make multiple requests to test connection pool
            responses = await asyncio.gather(
                client.get("/api/symbols"),
                client.get("/api/symbols"),
                client.get("/api/symbols")
            )
        
        # All requests should succeed
        assert all(r.status_code == 200 for r in responses)
        
        # Database should be called for each request (assuming no cache)
        assert mock_execute_query.call_count == 3
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_async_database_timeout_handling(self, mock_execute_query, mock_env_vars):
        """Test async database timeout handling."""
        # Mock timeout
        mock_execute_query.side_effect = asyncio.TimeoutError()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        # Should handle timeout gracefully
        assert response.status_code in [504, 500]
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_async_database_error_handling(self, mock_execute_query, mock_env_vars):
        """Test async database error handling."""
        # Mock database error
        mock_execute_query.side_effect = Exception("Database connection failed")
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        # Should handle database errors gracefully
        assert response.status_code in [500, 503]


class TestRedisIntegration:
    """Integration tests for Redis cache integration."""
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_redis_cache_miss_then_hit(self, mock_execute_query, mock_env_vars):
        """Test Redis cache miss followed by cache hit."""
        mock_execute_query.return_value = [('BTCUSDT',), ('ETHUSDT',)]
        
        with patch('cache_config.get_from_cache') as mock_get_cache:
            with patch('cache_config.set_in_cache') as mock_set_cache:
                # First request - cache miss
                mock_get_cache.return_value = None
                mock_set_cache.return_value = True
                
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response1 = await client.get("/api/symbols")
                
                assert response1.status_code == 200
                mock_get_cache.assert_called_once()
                mock_set_cache.assert_called_once()
                mock_execute_query.assert_called_once()
                
                # Reset mocks
                mock_get_cache.reset_mock()
                mock_set_cache.reset_mock()
                mock_execute_query.reset_mock()
                
                # Second request - cache hit
                mock_get_cache.return_value = ["BTCUSDT", "ETHUSDT"]
                
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response2 = await client.get("/api/symbols")
                
                assert response2.status_code == 200
                mock_get_cache.assert_called_once()
                mock_set_cache.assert_not_called()  # Should not set on cache hit
                mock_execute_query.assert_not_called()  # Should not query database on cache hit
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_redis_connection_failure_fallback(self, mock_execute_query, mock_env_vars):
        """Test fallback to database when Redis is unavailable."""
        mock_execute_query.return_value = [('BTCUSDT',), ('ETHUSDT',)]
        
        with patch('cache_config.get_from_cache', side_effect=Exception("Redis unavailable")):
            with patch('cache_config.set_in_cache', return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.get("/api/symbols")
                
                # Should still work with database fallback
                assert response.status_code == 200
                data = response.json()
                assert data == ["BTCUSDT", "ETHUSDT"]
                mock_execute_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_warming_integration(self, mock_env_vars):
        """Test cache warming functionality."""
        with patch('cache_config.warm_all_caches') as mock_warm:
            mock_warm.return_value = None
            
            # Test cache warming
            from cache_config import warm_all_caches
            await warm_all_caches()
            
            mock_warm.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_integration(self, mock_env_vars):
        """Test cache invalidation functionality."""
        with patch('cache_config.clear_cache_by_pattern') as mock_clear:
            mock_clear.return_value = 5
            
            # Test symbol cache invalidation
            from cache_config import invalidate_cache_for_symbol
            result = await invalidate_cache_for_symbol("BTCUSDT")
            
            assert result == 10  # 5 + 5 from two patterns
            assert mock_clear.call_count == 2  # Should clear two patterns
    
    @pytest.mark.asyncio
    async def test_cache_stats_integration(self, mock_env_vars):
        """Test cache statistics integration."""
        with patch('cache_config.get_cache_stats') as mock_stats:
            mock_stats.return_value = {
                "available": True,
                "hit_rate": 75.5,
                "used_memory": 1048576,
                "used_memory_human": "1M"
            }
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/cache/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert data["cache_stats"]["available"] is True
            assert data["cache_stats"]["hit_rate"] == 75.5


class TestCacheManagementEndpoints:
    """Integration tests for cache management endpoints."""
    
    @pytest.mark.asyncio
    async def test_cache_clear_endpoint(self, mock_env_vars):
        """Test cache clear endpoint."""
        with patch('cache_config.clear_cache_by_pattern') as mock_clear:
            mock_clear.return_value = 10
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/cache/clear?pattern=test:*")
            
            assert response.status_code == 200
            data = response.json()
            assert data["deleted_keys"] == 10
            assert data["pattern"] == "test:*"
            mock_clear.assert_called_once_with("test:*")
    
    @pytest.mark.asyncio
    async def test_cache_invalidate_symbol_endpoint(self, mock_env_vars):
        """Test cache invalidate symbol endpoint."""
        with patch('cache_config.invalidate_cache_for_symbol') as mock_invalidate:
            mock_invalidate.return_value = 5
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/cache/invalidate/symbol/BTCUSDT")
            
            assert response.status_code == 200
            data = response.json()
            assert data["deleted_keys"] == 5
            assert data["symbol"] == "BTCUSDT"
            mock_invalidate.assert_called_once_with("BTCUSDT")
    
    @pytest.mark.asyncio
    async def test_cache_invalidate_symbols_endpoint(self, mock_env_vars):
        """Test cache invalidate symbols endpoint."""
        with patch('cache_config.invalidate_symbols_cache') as mock_invalidate:
            mock_invalidate.return_value = True
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/cache/invalidate/symbols")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            mock_invalidate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_warm_endpoint(self, mock_env_vars):
        """Test cache warm endpoint."""
        with patch('cache_config.warm_all_caches') as mock_warm:
            mock_warm.return_value = None
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/cache/warm")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "initiated"


class TestStreamingEndpointIntegration:
    """Integration tests for streaming endpoint."""
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_streaming_endpoint_small_dataset(self, mock_execute_query, mock_env_vars):
        """Test streaming endpoint with small dataset."""
        # Mock small dataset (less than batch size)
        mock_execute_query.return_value = [
            ('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000),
            ('BTCUSDT', 'buy', 'MARKET', 'IOC', 0.002, None, 44500.0, 'FILLED', 0.002, 0.002, 1609459260000),
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders/stream",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"
        
        # Parse JSONL response
        lines = response.text.strip().split('\n')
        assert len(lines) == 2
        
        import json
        for line in lines:
            data = json.loads(line)
            assert "symbol" in data
            assert data["symbol"] == "BTCUSDT"
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_streaming_endpoint_large_dataset(self, mock_execute_query, mock_env_vars):
        """Test streaming endpoint with large dataset (multiple batches)."""
        # Mock large dataset that requires multiple batches
        def mock_query_side_effect(query, params):
            offset = params[-1]  # Last parameter is offset
            batch_size = params[-2]  # Second to last is batch size
            
            if offset == 0:
                # First batch
                return [
                    ('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000 + i)
                    for i in range(batch_size)
                ]
            else:
                # No more results
                return []
        
        mock_execute_query.side_effect = mock_query_side_effect
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders/stream",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000",
                    "batch_size": "5"
                }
            )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"
        
        # Should have called query twice (first batch + check for more)
        assert mock_execute_query.call_count == 2


class TestPaginationIntegration:
    """Integration tests for pagination functionality."""
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_pagination_with_timestamps(self, mock_execute_query, mock_env_vars):
        """Test pagination with timestamp range."""
        mock_execute_query.return_value = [
            ('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000),
            ('BTCUSDT', 'buy', 'MARKET', 'IOC', 0.002, None, 44500.0, 'FILLED', 0.002, 0.002, 1609459260000),
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000",
                    "page": "1",
                    "page_size": "10"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return pagination metadata
        assert "data" in data
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 10
        assert data["pagination"]["total_returned"] == 2
        assert len(data["data"]) == 2
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_pagination_with_limit(self, mock_execute_query, mock_env_vars):
        """Test that limit parameter bypasses pagination."""
        mock_execute_query.return_value = [
            ('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000),
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": "100",
                    "page": "2",  # Should be ignored
                    "page_size": "50"  # Should be ignored
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return simple array (no pagination metadata)
        assert isinstance(data, list)
        assert len(data) == 1


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""
    
    @pytest.mark.asyncio
    async def test_database_connection_error_handling(self, mock_env_vars):
        """Test handling of database connection errors."""
        with patch('app.async_execute_query', side_effect=Exception("Database connection failed")):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/symbols")
            
            assert response.status_code in [500, 503]
    
    @pytest.mark.asyncio
    async def test_cache_error_handling(self, mock_env_vars):
        """Test handling of cache errors."""
        with patch('app.async_execute_query') as mock_execute_query:
            mock_execute_query.return_value = [('BTCUSDT',)]
            
            with patch('cache_config.get_from_cache', side_effect=Exception("Cache error")):
                with patch('cache_config.set_in_cache', side_effect=Exception("Cache error")):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.get("/api/symbols")
                    
                    # Should still work with database fallback
                    assert response.status_code == 200
                    mock_execute_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_invalid_parameters_handling(self, mock_env_vars):
        """Test handling of invalid parameters."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test invalid timestamp
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "5m",
                    "start_timestamp": "invalid",
                    "end_timestamp": "1609462800000"
                }
            )
            
            assert response.status_code == 400
            
            # Test missing required parameters
            response = await client.get("/api/liquidations")
            assert response.status_code == 422  # Validation error


class TestCacheStampedePreventionIntegration:
    """Integration tests for cache stampede prevention."""
    
    @pytest.mark.asyncio
    @patch('app.async_execute_query')
    async def test_concurrent_cache_miss_handling(self, mock_execute_query, mock_env_vars):
        """Test handling of concurrent requests during cache miss."""
        mock_execute_query.return_value = [('BTCUSDT',), ('ETHUSDT',)]
        
        # Simulate cache miss for all requests
        with patch('cache_config.get_from_cache', return_value=None):
            with patch('cache_config.set_in_cache', return_value=True):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    # Make multiple concurrent requests
                    tasks = [client.get("/api/symbols") for _ in range(5)]
                    responses = await asyncio.gather(*tasks)
                
                # All requests should succeed
                assert all(r.status_code == 200 for r in responses)
                
                # Database should be called for each request (no stampede prevention yet)
                assert mock_execute_query.call_count == 5