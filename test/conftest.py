import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import asyncio


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("DB_HOST", "test_host")
    monkeypatch.setenv("DB_USER", "test_user")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("DB_DATABASE", "test_database")
    monkeypatch.setenv("DB_LIQ_TABLENAME", "test_table")
    
    # Redis environment variables
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_PASSWORD", "")
    monkeypatch.setenv("REDIS_DB", "0")
    monkeypatch.setenv("CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("CACHE_TTL_SYMBOLS", "3600")
    
    # Query timeout environment variables
    monkeypatch.setenv("QUERY_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("LONG_QUERY_TIMEOUT_SECONDS", "120")


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection and cursor."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=None)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=None)
    
    return mock_conn, mock_cursor


@pytest.fixture
def mock_async_db_connection():
    """Create a mock async database connection and cursor."""
    mock_cursor = AsyncMock()
    mock_conn = AsyncMock()
    
    # Mock async context manager behavior
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    
    # Mock cursor methods
    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchall = AsyncMock()
    mock_cursor.fetchone = AsyncMock()
    mock_cursor.close = AsyncMock()
    
    return mock_conn, mock_cursor


@pytest.fixture
def mock_redis_cache():
    """Create a mock Redis cache."""
    mock_redis = AsyncMock()
    
    # Mock Redis methods
    mock_redis.get = AsyncMock(return_value=None)  # Default to cache miss
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.keys = AsyncMock(return_value=[])
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    mock_redis.info = AsyncMock(return_value={
        'connected_clients': 1,
        'used_memory': 1024,
        'used_memory_human': '1K',
        'keyspace_hits': 100,
        'keyspace_misses': 50,
        'total_commands_processed': 1000
    })
    
    return mock_redis


@pytest.fixture
def mock_cache_available():
    """Mock cache availability."""
    with patch('cache_config.cache.is_available', True):
        with patch('cache_config.cache.get_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_get_client.return_value = mock_redis
            yield mock_redis


@pytest.fixture
def mock_cache_unavailable():
    """Mock cache unavailability."""
    with patch('cache_config.cache.is_available', False):
        with patch('cache_config.cache.get_client', return_value=None):
            yield


@pytest.fixture
def sample_liquidation_data():
    """Sample liquidation data for testing."""
    return [
        ('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5),
        ('BTCUSDT', 1609459200000, 1609459500000, 'sell', 200.75),
        ('BTCUSDT', 1609459500000, 1609459800000, 'buy', 150.25),
        ('BTCUSDT', 1609459500000, 1609459800000, 'sell', 175.0)
    ]


@pytest.fixture
def sample_symbols():
    """Sample symbols data for testing."""
    return [
        ('BTCUSDT',),
        ('ETHUSDT',),
        ('BNBUSDT',),
        ('ADAUSDT',),
        ('BTCUSDT123',),  # Should be filtered out
    ]


@pytest.fixture
def sample_liquidation_orders():
    """Sample liquidation order data for testing."""
    return [
        ('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000),
        ('BTCUSDT', 'buy', 'MARKET', 'IOC', 0.002, None, 44500.0, 'FILLED', 0.002, 0.002, 1609459260000),
        ('BTCUSDT', 'sell', 'LIMIT', 'FOK', 0.0015, 44800.0, 44800.0, 'FILLED', 0.0015, 0.0015, 1609459320000),
    ]