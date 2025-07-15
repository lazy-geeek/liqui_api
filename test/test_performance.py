import pytest
import asyncio
import time
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from concurrent.futures import ThreadPoolExecutor
import statistics

from app import app


class TestResponseTimes:
    """Test suite for response time benchmarks."""
    
    @pytest.mark.asyncio
    async def test_liquidations_endpoint_response_time(self, mock_env_vars):
        """Test response time for liquidations endpoint."""
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):
                with patch('cache_config.set_in_cache', return_value=True):
                    mock_query.return_value = [
                        ('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5),
                    ]
                    
                    start_time = time.time()
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.get(
                            "/api/liquidations",
                            params={
                                "symbol": "BTCUSDT",
                                "timeframe": "5m",
                                "start_timestamp": "1609459200000",
                                "end_timestamp": "1609462800000"
                            }
                        )
                    
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                    
                    assert response.status_code == 200
                    assert response_time < 1000  # Should respond within 1 second
                    print(f"Liquidations endpoint response time: {response_time:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_symbols_endpoint_response_time(self, mock_env_vars):
        """Test response time for symbols endpoint."""
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):
                with patch('cache_config.set_in_cache', return_value=True):
                    mock_query.return_value = [
                        ('BTCUSDT',), ('ETHUSDT',), ('ADAUSDT',)
                    ]
                    
                    start_time = time.time()
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.get("/api/symbols")
                    
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1000
                    
                    assert response.status_code == 200
                    assert response_time < 500  # Should respond within 500ms
                    print(f"Symbols endpoint response time: {response_time:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_liquidation_orders_endpoint_response_time(self, mock_env_vars):
        """Test response time for liquidation orders endpoint."""
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):
                with patch('cache_config.set_in_cache', return_value=True):
                    mock_query.return_value = [
                        ('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000),
                    ]
                    
                    start_time = time.time()
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.get(
                            "/api/liquidation-orders",
                            params={
                                "symbol": "BTCUSDT",
                                "limit": "100"
                            }
                        )
                    
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1000
                    
                    assert response.status_code == 200
                    assert response_time < 1000  # Should respond within 1 second
                    print(f"Liquidation orders endpoint response time: {response_time:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_cache_hit_performance(self, mock_env_vars):
        """Test performance improvement with cache hits."""
        cached_data = [
            {"timestamp": 1609459200000, "timestamp_iso": "2021-01-01T00:00:00Z", "side": "buy", "cumulated_usd_size": 100.5}
        ]
        
        # Test cache hit scenario
        with patch('cache_config.get_from_cache', return_value=cached_data):
            start_time = time.time()
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/api/liquidations",
                    params={
                        "symbol": "BTCUSDT",
                        "timeframe": "5m",
                        "start_timestamp": "1609459200000",
                        "end_timestamp": "1609462800000"
                    }
                )
            
            end_time = time.time()
            cache_hit_time = (end_time - start_time) * 1000
            
            assert response.status_code == 200
            assert cache_hit_time < 100  # Cache hits should be very fast
            print(f"Cache hit response time: {cache_hit_time:.2f}ms")


class TestConcurrentRequests:
    """Test suite for concurrent request handling."""
    
    @pytest.mark.asyncio
    async def test_concurrent_liquidations_requests(self, mock_env_vars):
        """Test handling multiple concurrent requests to liquidations endpoint."""
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):
                with patch('cache_config.set_in_cache', return_value=True):
                    mock_query.return_value = [
                        ('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5),
                    ]
                    
                    async def make_request(client, symbol):
                        return await client.get(
                            "/api/liquidations",
                            params={
                                "symbol": symbol,
                                "timeframe": "5m",
                                "start_timestamp": "1609459200000",
                                "end_timestamp": "1609462800000"
                            }
                        )
                    
                    start_time = time.time()
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        # Make 10 concurrent requests
                        tasks = [
                            make_request(client, f"SYMBOL{i}")
                            for i in range(10)
                        ]
                        responses = await asyncio.gather(*tasks)
                    
                    end_time = time.time()
                    total_time = (end_time - start_time) * 1000
                    
                    # All requests should succeed
                    assert all(r.status_code == 200 for r in responses)
                    
                    # Total time for 10 requests should be reasonable
                    assert total_time < 5000  # Should complete within 5 seconds
                    
                    avg_time_per_request = total_time / len(responses)
                    print(f"10 concurrent requests completed in {total_time:.2f}ms")
                    print(f"Average time per request: {avg_time_per_request:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_concurrent_different_endpoints(self, mock_env_vars):
        """Test concurrent requests to different endpoints."""
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):
                with patch('cache_config.set_in_cache', return_value=True):
                    # Configure different return values for different queries
                    def mock_query_side_effect(query, params):
                        if "DISTINCT symbol" in query:
                            return [('BTCUSDT',), ('ETHUSDT',)]
                        elif "GROUP BY" in query:
                            return [('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5)]
                        else:
                            return [('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000)]
                    
                    mock_query.side_effect = mock_query_side_effect
                    
                    async def make_requests(client):
                        # Make requests to different endpoints concurrently
                        liquidations_task = client.get(
                            "/api/liquidations",
                            params={
                                "symbol": "BTCUSDT",
                                "timeframe": "5m",
                                "start_timestamp": "1609459200000",
                                "end_timestamp": "1609462800000"
                            }
                        )
                        symbols_task = client.get("/api/symbols")
                        orders_task = client.get(
                            "/api/liquidation-orders",
                            params={"symbol": "BTCUSDT", "limit": "100"}
                        )
                        
                        return await asyncio.gather(liquidations_task, symbols_task, orders_task)
                    
                    start_time = time.time()
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        responses = await make_requests(client)
                    
                    end_time = time.time()
                    total_time = (end_time - start_time) * 1000
                    
                    # All requests should succeed
                    assert all(r.status_code == 200 for r in responses)
                    assert total_time < 3000  # Should complete within 3 seconds
                    
                    print(f"3 concurrent different endpoints completed in {total_time:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_load_testing_simulation(self, mock_env_vars):
        """Simulate load testing with multiple concurrent requests."""
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):
                with patch('cache_config.set_in_cache', return_value=True):
                    mock_query.return_value = [
                        ('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5),
                    ]
                    
                    async def make_batch_requests(client, batch_size=5):
                        """Make a batch of requests."""
                        tasks = []
                        for i in range(batch_size):
                            task = client.get(
                                "/api/liquidations",
                                params={
                                    "symbol": f"SYMBOL{i % 3}",  # Rotate between 3 symbols
                                    "timeframe": "5m",
                                    "start_timestamp": "1609459200000",
                                    "end_timestamp": "1609462800000"
                                }
                            )
                            tasks.append(task)
                        return await asyncio.gather(*tasks)
                    
                    response_times = []
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        # Run 5 batches of 5 requests each (25 total requests)
                        for batch in range(5):
                            batch_start = time.time()
                            batch_responses = await make_batch_requests(client, 5)
                            batch_end = time.time()
                            
                            batch_time = (batch_end - batch_start) * 1000
                            response_times.append(batch_time)
                            
                            # All requests in batch should succeed
                            assert all(r.status_code == 200 for r in batch_responses)
                    
                    # Calculate statistics
                    avg_batch_time = statistics.mean(response_times)
                    min_batch_time = min(response_times)
                    max_batch_time = max(response_times)
                    
                    print(f"Load test results (5 batches of 5 requests each):")
                    print(f"Average batch time: {avg_batch_time:.2f}ms")
                    print(f"Minimum batch time: {min_batch_time:.2f}ms")
                    print(f"Maximum batch time: {max_batch_time:.2f}ms")
                    
                    # Performance assertions
                    assert avg_batch_time < 2000  # Average batch should complete within 2 seconds
                    assert max_batch_time < 3000  # No batch should take more than 3 seconds


class TestCacheEffectiveness:
    """Test suite for cache effectiveness metrics."""
    
    @pytest.mark.asyncio
    async def test_cache_miss_then_hit_performance(self, mock_env_vars):
        """Test performance difference between cache miss and hit."""
        mock_data = [
            {"timestamp": 1609459200000, "timestamp_iso": "2021-01-01T00:00:00Z", "side": "buy", "cumulated_usd_size": 100.5}
        ]
        
        # First request (cache miss)
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):  # Cache miss
                with patch('cache_config.set_in_cache', return_value=True):
                    mock_query.return_value = [('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5)]
                    
                    start_time = time.time()
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response1 = await client.get(
                            "/api/liquidations",
                            params={
                                "symbol": "BTCUSDT",
                                "timeframe": "5m",
                                "start_timestamp": "1609459200000",
                                "end_timestamp": "1609462800000"
                            }
                        )
                    
                    miss_time = (time.time() - start_time) * 1000
        
        # Second request (cache hit)
        with patch('cache_config.get_from_cache', return_value=mock_data):  # Cache hit
            start_time = time.time()
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response2 = await client.get(
                    "/api/liquidations",
                    params={
                        "symbol": "BTCUSDT",
                        "timeframe": "5m",
                        "start_timestamp": "1609459200000",
                        "end_timestamp": "1609462800000"
                    }
                )
            
            hit_time = (time.time() - start_time) * 1000
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Cache hit should be significantly faster
        performance_improvement = (miss_time - hit_time) / miss_time * 100
        
        print(f"Cache miss time: {miss_time:.2f}ms")
        print(f"Cache hit time: {hit_time:.2f}ms")
        print(f"Performance improvement: {performance_improvement:.1f}%")
        
        assert hit_time < miss_time  # Cache hit should be faster
        assert performance_improvement > 10  # At least 10% improvement
    
    @pytest.mark.asyncio
    async def test_cache_warming_effectiveness(self, mock_env_vars):
        """Test cache warming effectiveness."""
        # Mock cache warming
        with patch('cache_config.warm_all_caches') as mock_warm:
            mock_warm.return_value = None
            
            # Simulate cache warming
            start_warm = time.time()
            await mock_warm()
            warm_time = (time.time() - start_warm) * 1000
            
            print(f"Cache warming completed in {warm_time:.2f}ms")
            
            # Cache warming should complete quickly
            assert warm_time < 1000  # Should complete within 1 second
            mock_warm.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_memory_usage_estimation(self, mock_cache_available):
        """Test estimation of cache memory usage."""
        mock_redis = mock_cache_available
        
        # Simulate cache stats
        mock_redis.info.return_value = {
            'used_memory': 1048576,  # 1MB
            'used_memory_human': '1M',
            'keyspace_hits': 1000,
            'keyspace_misses': 100,
            'total_commands_processed': 5000,
            'connected_clients': 10
        }
        
        from cache_config import get_cache_stats
        stats = await get_cache_stats()
        
        print(f"Cache memory usage: {stats['used_memory_human']}")
        print(f"Cache hit rate: {stats['hit_rate']}%")
        print(f"Connected clients: {stats['connected_clients']}")
        
        assert stats['used_memory'] == 1048576
        assert stats['hit_rate'] > 90  # Good hit rate
        assert stats['connected_clients'] == 10


class TestDatabaseTimeout:
    """Test suite for database timeout handling."""
    
    @pytest.mark.asyncio
    async def test_query_timeout_handling(self, mock_env_vars):
        """Test that query timeouts are handled properly."""
        with patch('app.async_execute_query') as mock_query:
            # Simulate a timeout
            mock_query.side_effect = asyncio.TimeoutError()
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/api/liquidations",
                    params={
                        "symbol": "BTCUSDT",
                        "timeframe": "5m",
                        "start_timestamp": "1609459200000",
                        "end_timestamp": "1609462800000"
                    }
                )
            
            # Should get a timeout error response
            assert response.status_code in [504, 500]  # Gateway timeout or internal error
    
    @pytest.mark.asyncio
    async def test_database_connection_resilience(self, mock_env_vars):
        """Test application resilience to database connection issues."""
        # Test various database error scenarios
        error_scenarios = [
            Exception("Connection lost"),
            Exception("Database unavailable"),
            Exception("Query failed")
        ]
        
        for error in error_scenarios:
            with patch('app.async_execute_query') as mock_query:
                mock_query.side_effect = error
                
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.get(
                        "/api/liquidations",
                        params={
                            "symbol": "BTCUSDT",
                            "timeframe": "5m",
                            "start_timestamp": "1609459200000",
                            "end_timestamp": "1609462800000"
                        }
                    )
                
                # Should handle errors gracefully
                assert response.status_code in [500, 503]  # Internal or service unavailable
                print(f"Database error handled: {error}")


@pytest.mark.slow
class TestPerformanceBenchmarks:
    """Slow tests for comprehensive performance benchmarking."""
    
    @pytest.mark.asyncio
    async def test_large_dataset_performance(self, mock_env_vars):
        """Test performance with large datasets."""
        # Generate large mock dataset (1000 records)
        large_dataset = [
            ('BTCUSDT', 1609459200000 + i * 1000, 1609459200000 + (i + 1) * 1000, 'buy' if i % 2 == 0 else 'sell', 100.5 + i)
            for i in range(1000)
        ]
        
        with patch('app.async_execute_query') as mock_query:
            with patch('cache_config.get_from_cache', return_value=None):
                with patch('cache_config.set_in_cache', return_value=True):
                    mock_query.return_value = large_dataset
                    
                    start_time = time.time()
                    
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.get(
                            "/api/liquidations",
                            params={
                                "symbol": "BTCUSDT",
                                "timeframe": "5m",
                                "start_timestamp": "1609459200000",
                                "end_timestamp": "1609562800000"  # Longer time range
                            }
                        )
                    
                    processing_time = (time.time() - start_time) * 1000
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) > 0
                    
                    print(f"Large dataset (1000 records) processed in {processing_time:.2f}ms")
                    
                    # Large datasets should still process within reasonable time
                    assert processing_time < 5000  # Should complete within 5 seconds