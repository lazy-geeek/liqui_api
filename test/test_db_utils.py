import pytest
from unittest.mock import MagicMock, patch, call
import mysql.connector
from fastapi import HTTPException
from app import db_connection, db_error_handler, execute_query, get_db_cursor


class TestDbConnection:
    """Tests for db_connection context manager."""
    
    @patch('app.get_db_connection')
    def test_successful_connection_and_cleanup(self, mock_get_db_connection):
        """Test successful connection lifecycle and cleanup."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Use context manager
        with db_connection() as cursor:
            assert cursor == mock_cursor
        
        # Verify cleanup
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('app.get_db_connection')
    def test_cleanup_on_exception(self, mock_get_db_connection):
        """Test cleanup when exception occurs during query."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Use context manager with exception
        with pytest.raises(ValueError):
            with db_connection() as cursor:
                raise ValueError("Test exception")
        
        # Verify cleanup still happens
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('app.get_db_connection')
    def test_cleanup_when_connection_fails(self, mock_get_db_connection):
        """Test behavior when connection fails."""
        # Setup mock to raise exception
        mock_get_db_connection.side_effect = HTTPException(
            status_code=503, 
            detail="Database service unavailable"
        )
        
        # Verify exception is propagated
        with pytest.raises(HTTPException) as exc_info:
            with db_connection() as cursor:
                pass
        
        assert exc_info.value.status_code == 503
    
    @patch('app.get_db_connection')
    def test_cursor_and_conn_close_called(self, mock_get_db_connection):
        """Verify cursor.close() and conn.close() are called."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Track method calls
        with db_connection() as cursor:
            pass
        
        # Verify both close methods called
        assert mock_cursor.close.called
        assert mock_conn.close.called


class TestDbErrorHandler:
    """Tests for db_error_handler decorator."""
    
    @pytest.mark.asyncio
    async def test_mysql_error_handling(self):
        """Test mysql.connector.Error → HTTPException(500)."""
        @db_error_handler("/test/endpoint")
        async def test_func():
            raise mysql.connector.Error("Connection failed")
        
        with pytest.raises(HTTPException) as exc_info:
            await test_func()
        
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal database error"
    
    @pytest.mark.asyncio
    async def test_http_exception_passthrough(self):
        """Test HTTPException pass-through unchanged."""
        @db_error_handler("/test/endpoint")
        async def test_func():
            raise HTTPException(status_code=404, detail="Not found")
        
        with pytest.raises(HTTPException) as exc_info:
            await test_func()
        
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Not found"
    
    @pytest.mark.asyncio
    async def test_generic_exception_handling(self):
        """Test generic Exception → HTTPException(500)."""
        @db_error_handler("/test/endpoint")
        async def test_func():
            raise ValueError("Unexpected error")
        
        with pytest.raises(HTTPException) as exc_info:
            await test_func()
        
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal server error"
    
    @pytest.mark.asyncio
    @patch('builtins.print')
    async def test_error_logging_includes_endpoint(self, mock_print):
        """Verify error logging includes endpoint name."""
        @db_error_handler("/test/endpoint")
        async def test_func():
            raise mysql.connector.Error("Test error")
        
        with pytest.raises(HTTPException):
            await test_func()
        
        # Verify logging includes endpoint name
        mock_print.assert_called_with(
            "ERROR: Database error in /test/endpoint: Test error"
        )


class TestExecuteQuery:
    """Tests for execute_query helper function."""
    
    @pytest.mark.asyncio
    @patch('app.db_connection')
    async def test_fetch_all_mode(self, mock_db_connection):
        """Test with fetch_all=True (default)."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_db_connection.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [('row1',), ('row2',)]
        
        # Execute query
        result = await execute_query("SELECT * FROM test", ())
        
        # Verify
        assert result == [('row1',), ('row2',)]
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test", ())
        mock_cursor.fetchall.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.db_connection')
    async def test_fetch_one_mode(self, mock_db_connection):
        """Test with fetch_all=False."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_db_connection.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ('single_row',)
        
        # Execute query
        result = await execute_query("SELECT * FROM test LIMIT 1", (), fetch_all=False)
        
        # Verify
        assert result == [('single_row',)]
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test LIMIT 1", ())
        mock_cursor.fetchone.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.db_connection')
    async def test_parameter_binding(self, mock_db_connection):
        """Test parameter binding works correctly."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_db_connection.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [('BTCUSDT',)]
        
        # Execute query with parameters
        params = ('btcusdt', 1000, 2000)
        query = "SELECT * FROM table WHERE symbol = %s AND time BETWEEN %s AND %s"
        result = await execute_query(query, params)
        
        # Verify parameters passed correctly
        mock_cursor.execute.assert_called_once_with(query, params)
    
    @pytest.mark.asyncio
    @patch('app.db_connection')
    async def test_empty_results(self, mock_db_connection):
        """Test with empty results."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_db_connection.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        
        # Execute query
        result = await execute_query("SELECT * FROM empty_table", ())
        
        # Verify
        assert result == []
    
    @pytest.mark.asyncio
    @patch('app.db_connection')
    async def test_fetch_one_with_no_result(self, mock_db_connection):
        """Test fetch_one mode with no result."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_db_connection.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        
        # Execute query
        result = await execute_query("SELECT * FROM test WHERE 1=0", (), fetch_all=False)
        
        # Verify
        assert result is None


class TestFastAPIDependency:
    """Tests for get_db_cursor FastAPI dependency."""
    
    @patch('app.get_db_connection')
    def test_dependency_successful_flow(self, mock_get_db_connection):
        """Test successful cursor creation and cleanup in dependency."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Use dependency
        gen = get_db_cursor()
        cursor = next(gen)
        
        # Verify cursor returned
        assert cursor == mock_cursor
        
        # Trigger cleanup
        try:
            next(gen)
        except StopIteration:
            pass
        
        # Verify cleanup
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('app.get_db_connection')
    def test_dependency_cleanup_on_exception(self, mock_get_db_connection):
        """Test cleanup when exception occurs during dependency use."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Use dependency with exception
        gen = get_db_cursor()
        cursor = next(gen)
        
        # Simulate exception during use
        try:
            gen.throw(ValueError("Test exception"))
        except ValueError:
            pass
        
        # Verify cleanup still happens
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('app.get_db_connection')
    def test_dependency_vs_context_manager_comparison(self, mock_get_db_connection):
        """Test that dependency and context manager behave similarly."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.is_connected.return_value = True
        
        # Test dependency
        gen = get_db_cursor()
        dep_cursor = next(gen)
        try:
            next(gen)
        except StopIteration:
            pass
        
        # Reset mocks
        mock_cursor.reset_mock()
        mock_conn.reset_mock()
        
        # Test context manager
        with db_connection() as ctx_cursor:
            pass
        
        # Both should have same cleanup behavior
        assert mock_cursor.close.call_count == 1
        assert mock_conn.close.call_count == 1