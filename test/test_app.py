import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone
import mysql.connector
from app import app, get_db_connection


class TestDatabaseConnection:
    """Test suite for database connection handling."""
    
    @patch('app.mysql.connector.connect')
    def test_successful_database_connection(self, mock_connect, mock_env_vars):
        """Test successful database connection."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        conn = get_db_connection()
        
        assert conn == mock_conn
        mock_connect.assert_called_once()
    
    @patch('app.mysql.connector.connect')
    def test_database_connection_failure(self, mock_connect, mock_env_vars):
        """Test database connection failure handling (503 error)."""
        mock_connect.side_effect = mysql.connector.Error("Connection failed")
        
        with pytest.raises(Exception) as exc_info:
            get_db_connection()
        
        assert exc_info.value.status_code == 503
        assert "Database service unavailable" in str(exc_info.value.detail)


class TestLiquidationsEndpoint:
    """Test suite for /api/liquidations endpoint."""
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_valid_symbol_and_timeframe(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_liquidation_data):
        """Test with valid symbol and timeframe."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_liquidation_data
        
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
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4
        assert all(isinstance(item["cumulated_usd_size"], float) for item in data)
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_timestamp_parsing_unix_milliseconds(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test timestamp parsing (Unix milliseconds)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = [('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5)]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 200
        mock_cursor.execute.assert_called_once()
        args = mock_cursor.execute.call_args[0][1]
        assert args[9] == "btcusdt"  # Symbol should be lowercase
        assert args[10] == 1609459200000  # Start timestamp
        assert args[11] == 1609462800000  # End timestamp
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_timestamp_parsing_iso_format(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test timestamp parsing (ISO format)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = [('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5)]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "2021-01-01T00:00:00",
                    "end_timestamp": "2021-01-01T01:00:00"
                }
            )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_invalid_timestamp_format(self, mock_env_vars):
        """Test invalid timestamp format (400 error)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "invalid",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 400
        assert "must be valid Unix timestamps" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_negative_timestamps(self, mock_env_vars):
        """Test negative timestamps (400 error)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "-1000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 400
        assert "must be non-negative integers" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_start_timestamp_after_end_timestamp(self, mock_env_vars):
        """Test start_timestamp > end_timestamp (400 error)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "1609462800000",
                    "end_timestamp": "1609459200000"
                }
            )
        
        assert response.status_code == 400
        assert "start_timestamp must be before end_timestamp" in response.json()["detail"]
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_no_data_found(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test no data found (404 error)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = []
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 404
        assert "No data found" in response.json()["detail"]
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_database_error_handling(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test database error handling (500 error)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.execute.side_effect = mysql.connector.Error("Query failed")
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 500
        assert "Internal database error" in response.json()["detail"]
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_timeframe_conversion(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test timeframe conversion (5m, 1h, 1d)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = [('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5)]
        
        timeframes = [
            ("5m", 5 * 60 * 1000),
            ("1h", 3600 * 1000),
            ("1d", 86400 * 1000)
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for timeframe, expected_ms in timeframes:
                response = await client.get(
                    "/api/liquidations",
                    params={
                        "symbol": "BTCUSDT",
                        "timeframe": timeframe,
                        "start_timestamp": "1609459200000",
                        "end_timestamp": "1609462800000"
                    }
                )
                
                assert response.status_code == 200
                args = mock_cursor.execute.call_args[0][1]
                assert args[1] == expected_ms  # Check timeframe in milliseconds
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_symbol_case_insensitivity(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test symbol case-insensitivity."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = [('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5)]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 200
        args = mock_cursor.execute.call_args[0][1]
        assert args[9] == "btcusdt"  # Should be lowercase
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_connection_cleanup_on_success(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test database connection cleanup on success."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = [('BTCUSDT', 1609459200000, 1609459500000, 'buy', 100.5)]
        mock_conn.is_connected.return_value = True
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 200
        mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_connection_cleanup_on_error(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test database connection cleanup on error."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.execute.side_effect = mysql.connector.Error("Query failed")
        mock_conn.is_connected.return_value = True
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidations",
                params={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 500
        mock_conn.close.assert_called_once()


class TestSymbolsEndpoint:
    """Test suite for /api/symbols endpoint."""
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_successful_symbol_retrieval(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_symbols):
        """Test successful symbol retrieval."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_symbols
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        assert response.status_code == 200
        symbols = response.json()
        assert len(symbols) == 5  # Including the one that ends with numbers
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols
        assert "BTCUSDT123" in symbols  # Should be included in raw results
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_filtering_symbols_ending_with_numbers(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test filtering of symbols ending with numbers."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        # The filtering happens in SQL, so we simulate filtered results
        mock_cursor.fetchall.return_value = [
            ('BTCUSDT',),
            ('ETHUSDT',),
            ('BNBUSDT',),
            ('ADAUSDT',)
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        assert response.status_code == 200
        symbols = response.json()
        assert all(not symbol[-1].isdigit() for symbol in symbols)
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_empty_result_handling(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test empty result handling."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = []
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        assert response.status_code == 200
        assert response.json() == []
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_database_error_handling(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test database error handling (500 error)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.execute.side_effect = mysql.connector.Error("Query failed")
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        assert response.status_code == 500
        assert "Internal database error" in response.json()["detail"]
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_connection_cleanup_on_error(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test connection cleanup on error."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.execute.side_effect = mysql.connector.Error("Query failed")
        mock_conn.is_connected.return_value = True
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        assert response.status_code == 500
        mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_connection_cleanup_on_success(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test connection cleanup on success."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = [('BTCUSDT',), ('ETHUSDT',)]
        mock_conn.is_connected.return_value = True
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
        
        assert response.status_code == 200
        mock_conn.close.assert_called_once()


class TestLiquidationOrdersEndpoint:
    """Test suite for /api/liquidation-orders endpoint."""
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_with_valid_timestamp_range(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_liquidation_orders):
        """Test with valid timestamp range."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_liquidation_orders
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 200
        orders = response.json()
        assert len(orders) == 3
        assert orders[0]["symbol"] == "BTCUSDT"
        assert orders[0]["side"] == "sell"
        assert orders[0]["order_type"] == "LIMIT"
        assert orders[0]["original_quantity"] == 0.001
        assert orders[0]["price"] == 45000.0
        assert orders[1]["symbol"] == "BTCUSDT"
        assert orders[1]["price"] is None  # MARKET order has no price
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_with_valid_limit_parameter(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_liquidation_orders):
        """Test with valid limit parameter."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_liquidation_orders[:2]  # Return only 2 orders
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 2
                }
            )
        
        assert response.status_code == 200
        orders = response.json()
        assert len(orders) == 2
    
    @pytest.mark.asyncio
    async def test_parameter_validation_both_timestamps_and_limit(self, mock_env_vars):
        """Test parameter validation (both timestamps and limit provided)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "1609459200000",
                    "end_timestamp": "1609462800000",
                    "limit": 10
                }
            )
        
        assert response.status_code == 400
        assert "Cannot provide both timestamp range and limit" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_parameter_validation_neither_timestamps_nor_limit(self, mock_env_vars):
        """Test parameter validation (neither timestamps nor limit provided)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT"
                }
            )
        
        assert response.status_code == 400
        assert "Either provide both timestamps or a limit parameter" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_parameter_validation_only_start_timestamp(self, mock_env_vars):
        """Test parameter validation (only start_timestamp provided)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "1609459200000"
                }
            )
        
        assert response.status_code == 400
        assert "Both start_timestamp and end_timestamp must be provided together" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_parameter_validation_only_end_timestamp(self, mock_env_vars):
        """Test parameter validation (only end_timestamp provided)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 400
        assert "Both start_timestamp and end_timestamp must be provided together" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_limit_validation_negative_number(self, mock_env_vars):
        """Test limit validation (negative number)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": -5
                }
            )
        
        assert response.status_code == 422  # FastAPI validation error
    
    @pytest.mark.asyncio
    async def test_limit_validation_zero(self, mock_env_vars):
        """Test limit validation (zero)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 0
                }
            )
        
        assert response.status_code == 422  # FastAPI validation error
    
    @pytest.mark.asyncio
    async def test_limit_validation_exceeds_maximum(self, mock_env_vars):
        """Test limit validation (exceeds maximum)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 1001
                }
            )
        
        assert response.status_code == 422  # FastAPI validation error
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_404_when_no_orders_found(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test 404 when no orders found."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = []
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 10
                }
            )
        
        assert response.status_code == 404
        assert "No liquidation orders found" in response.json()["detail"]
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_symbol_case_insensitivity(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_liquidation_orders):
        """Test symbol case-insensitivity."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_liquidation_orders
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 10
                }
            )
        
        assert response.status_code == 200
        args = mock_cursor.execute.call_args[0][1]
        assert args[0] == "btcusdt"  # Should be lowercase
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_decimal_to_float_conversion(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test decimal to float conversion."""
        from decimal import Decimal
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        # Return decimals to test conversion
        mock_cursor.fetchall.return_value = [
            ('BTCUSDT', 'sell', 'LIMIT', 'GTC', Decimal('0.001'), Decimal('45000.0'), Decimal('45000.0'), 'FILLED', Decimal('0.001'), Decimal('0.001'), 1609459200000),
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 1
                }
            )
        
        assert response.status_code == 200
        orders = response.json()
        assert isinstance(orders[0]["original_quantity"], float)
        assert isinstance(orders[0]["price"], float)
        assert orders[0]["original_quantity"] == 0.001
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_order_sorting_newest_first(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_liquidation_orders):
        """Test order sorting (newest first)."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_liquidation_orders
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 10
                }
            )
        
        assert response.status_code == 200
        # Check that the query includes ORDER BY order_trade_time DESC
        query = mock_cursor.execute.call_args[0][0]
        assert "ORDER BY order_trade_time DESC" in query
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_timestamp_parsing_iso_format(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_liquidation_orders):
        """Test timestamp parsing in ISO format."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_liquidation_orders
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "2021-01-01T00:00:00+00:00",
                    "end_timestamp": "2021-01-01T01:00:00+00:00"
                }
            )
        
        assert response.status_code == 200
        # Check that timestamps were parsed correctly
        args = mock_cursor.execute.call_args[0][1]
        assert args[1] == 1609459200000  # start_timestamp
        assert args[2] == 1609462800000  # end_timestamp
    
    @pytest.mark.asyncio
    async def test_invalid_timestamp_format(self, mock_env_vars):
        """Test invalid timestamp format."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "invalid",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 400
        assert "Invalid timestamp format" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_negative_timestamps(self, mock_env_vars):
        """Test negative timestamps."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "-1000",
                    "end_timestamp": "1609462800000"
                }
            )
        
        assert response.status_code == 400
        assert "Timestamps must be non-negative" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_start_timestamp_after_end_timestamp(self, mock_env_vars):
        """Test start_timestamp > end_timestamp."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "start_timestamp": "1609462800000",
                    "end_timestamp": "1609459200000"
                }
            )
        
        assert response.status_code == 400
        assert "start_timestamp must be before end_timestamp" in response.json()["detail"]
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_database_error_handling(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test database error handling."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.execute.side_effect = mysql.connector.Error("Query failed")
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 10
                }
            )
        
        assert response.status_code == 500
        assert "Internal database error" in response.json()["detail"]
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_connection_cleanup_on_success(self, mock_get_conn, mock_env_vars, mock_db_connection, sample_liquidation_orders):
        """Test connection cleanup on success."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.fetchall.return_value = sample_liquidation_orders
        mock_conn.is_connected.return_value = True
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 10
                }
            )
        
        assert response.status_code == 200
        mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.get_db_connection')
    async def test_connection_cleanup_on_error(self, mock_get_conn, mock_env_vars, mock_db_connection):
        """Test connection cleanup on error."""
        mock_conn, mock_cursor = mock_db_connection
        mock_get_conn.return_value = mock_conn
        mock_cursor.execute.side_effect = mysql.connector.Error("Query failed")
        mock_conn.is_connected.return_value = True
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 10
                }
            )
        
        assert response.status_code == 500
        mock_conn.close.assert_called_once()
