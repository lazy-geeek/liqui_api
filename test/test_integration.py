import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock
import mysql.connector
from app import app


class TestIntegration:
    """Integration tests for the API endpoints."""
    
    @pytest.mark.asyncio
    @patch('app.mysql.connector.connect')
    async def test_complete_liquidations_flow(self, mock_connect, mock_env_vars):
        """Test complete request/response cycle for liquidations endpoint."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Mock cursor context manager
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        
        # Mock data
        mock_cursor.fetchall.return_value = [
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
            assert data[0]["side"] == "buy"
            assert data[0]["cumulated_usd_size"] == 100.5
            assert data[1]["side"] == "sell"
            assert data[1]["cumulated_usd_size"] == 200.75
            
            # Verify database interaction
            mock_connect.assert_called_once()
            mock_cursor.execute.assert_called_once()
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.mysql.connector.connect')
    async def test_complete_symbols_flow(self, mock_connect, mock_env_vars):
        """Test complete request/response cycle for symbols endpoint."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Mock data
        mock_cursor.fetchall.return_value = [
            ('BTCUSDT',),
            ('ETHUSDT',),
            ('BNBUSDT',),
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Make request
            response = await client.get("/api/symbols")
            
            # Verify response
            assert response.status_code == 200
            symbols = response.json()
            assert len(symbols) == 3
            assert "BTCUSDT" in symbols
            assert "ETHUSDT" in symbols
            assert "BNBUSDT" in symbols
            
            # Verify database interaction
            mock_connect.assert_called_once()
            mock_cursor.execute.assert_called_once()
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.mysql.connector.connect')
    async def test_complete_liquidation_orders_flow(self, mock_connect, mock_env_vars):
        """Test complete request/response cycle for liquidation-orders endpoint."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Mock data
        mock_cursor.fetchall.return_value = [
            ('BTCUSDT', 'sell', 'LIMIT', 'GTC', 0.001, 45000.0, 45000.0, 'FILLED', 0.001, 0.001, 1609459200000),
            ('BTCUSDT', 'buy', 'MARKET', 'IOC', 0.002, None, 44500.0, 'FILLED', 0.002, 0.002, 1609459260000),
        ]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test with limit
            response = await client.get(
                "/api/liquidation-orders",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 10
                }
            )
            
            # Verify response
            assert response.status_code == 200
            orders = response.json()
            assert len(orders) == 2
            assert orders[0]["symbol"] == "BTCUSDT"
            assert orders[0]["side"] == "sell"
            assert orders[0]["order_type"] == "LIMIT"
            assert orders[0]["price"] == 45000.0
            assert orders[1]["symbol"] == "BTCUSDT"
            assert orders[1]["side"] == "buy"
            assert orders[1]["order_type"] == "MARKET"
            assert orders[1]["price"] is None
            
            # Verify database interaction
            mock_connect.assert_called_once()
            mock_cursor.execute.assert_called_once()
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.mysql.connector.connect')
    async def test_concurrent_requests(self, mock_connect, mock_env_vars):
        """Test handling of concurrent requests."""
        # Setup mock connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Mock data for symbols
        mock_cursor.fetchall.return_value = [('BTCUSDT',), ('ETHUSDT',)]
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Make concurrent requests
            import asyncio
            responses = await asyncio.gather(
                client.get("/api/symbols"),
                client.get("/api/symbols"),
                client.get("/api/symbols"),
            )
            
            # Verify all responses are successful
            for response in responses:
                assert response.status_code == 200
                symbols = response.json()
                assert len(symbols) == 2
            
            # Verify multiple database connections were made
            assert mock_connect.call_count == 3
    
    @pytest.mark.asyncio
    @patch('app.mysql.connector.connect')
    async def test_error_handling_integration(self, mock_connect, mock_env_vars):
        """Test error handling across the application."""
        # Test database connection failure
        mock_connect.side_effect = mysql.connector.Error("Connection failed")
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/symbols")
            # The get_db_connection raises HTTPException(503) which is now properly
            # propagated through the db_error_handler decorator
            assert response.status_code == 503
            assert "Database service unavailable" in response.json()["detail"]