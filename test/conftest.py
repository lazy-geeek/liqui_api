import pytest
import os
from unittest.mock import MagicMock, patch
from datetime import datetime


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("DB_HOST", "test_host")
    monkeypatch.setenv("DB_USER", "test_user")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("DB_DATABASE", "test_database")
    monkeypatch.setenv("DB_LIQ_TABLENAME", "test_table")


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