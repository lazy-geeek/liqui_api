import aiomysql
import os
from contextlib import asynccontextmanager
from functools import wraps
from typing import AsyncGenerator, Optional, List, Tuple, Callable, Any
from fastapi import HTTPException


# MySQL database configuration from environment variables
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "db": os.getenv("DB_DATABASE"),  # aiomysql uses 'db' not 'database'
}

# Connection pool configuration
POOL_CONFIG = {
    "minsize": 5,
    "maxsize": 20,
    "pool_recycle": 3600,  # Recycle connections after 1 hour
    "autocommit": True,
}

# Query timeout configuration (in seconds)
QUERY_TIMEOUT = int(os.getenv("QUERY_TIMEOUT_SECONDS", "30"))  # Default 30 seconds
LONG_QUERY_TIMEOUT = int(os.getenv("LONG_QUERY_TIMEOUT_SECONDS", "120"))  # Default 2 minutes for heavy queries

# Global connection pool
_pool: Optional[aiomysql.Pool] = None


async def initialize_pool() -> aiomysql.Pool:
    """
    Initialize the async MySQL connection pool.
    
    Returns:
        aiomysql.Pool: The initialized connection pool
        
    Raises:
        Exception: If pool initialization fails
    """
    global _pool
    if _pool is None:
        try:
            _pool = await aiomysql.create_pool(
                **db_config,
                **POOL_CONFIG
            )
            print("INFO: Async MySQL connection pool initialized successfully")
        except Exception as err:
            print(f"FATAL: Could not initialize async database pool: {err}")
            raise
    return _pool


async def get_pool() -> aiomysql.Pool:
    """
    Get the connection pool, initializing it if necessary.
    
    Returns:
        aiomysql.Pool: The connection pool
    """
    global _pool
    if _pool is None:
        await initialize_pool()
    return _pool


async def close_pool() -> None:
    """
    Close the connection pool and all its connections.
    """
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        print("INFO: Async MySQL connection pool closed")


# ==================== Async Database Utilities ====================

@asynccontextmanager
async def async_db_connection() -> AsyncGenerator[aiomysql.Cursor, None]:
    """
    Async context manager for database connections with automatic cleanup.
    
    Yields:
        aiomysql.Cursor: Database cursor for executing queries
        
    Raises:
        HTTPException: If database connection fails
    """
    pool = await get_pool()
    conn = None
    cursor = None
    try:
        conn = await pool.acquire()
        cursor = await conn.cursor()
        yield cursor
    except Exception as err:
        print(f"ERROR: Database connection error: {err}")
        raise HTTPException(status_code=503, detail="Database service unavailable")
    finally:
        if cursor:
            await cursor.close()
        if conn:
            await pool.release(conn)


def async_db_error_handler(endpoint_name: str) -> Callable:
    """
    Decorator for consistent async database error handling.
    
    Args:
        endpoint_name: Name of the endpoint for error logging
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except aiomysql.Error as err:
                print(f"ERROR: Database error in {endpoint_name}: {err}")
                raise HTTPException(status_code=500, detail="Internal database error")
            except HTTPException:
                raise  # Re-raise HTTP exceptions as-is
            except Exception as e:
                print(f"ERROR: Unexpected error in {endpoint_name}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        return wrapper
    return decorator


async def async_execute_query(
    query: str, 
    params: Tuple = (), 
    fetch_all: bool = True,
    timeout: Optional[int] = None
) -> Optional[List[Tuple[Any, ...]]]:
    """
    Execute an async database query with proper error handling and timeout.
    
    Args:
        query: SQL query string
        params: Query parameters tuple
        fetch_all: If True, uses fetchall(), otherwise fetchone()
        timeout: Query timeout in seconds (uses default if None)
        
    Returns:
        Query results or None
    """
    import asyncio
    
    # Determine timeout - use long timeout for streaming/large queries
    if timeout is None:
        timeout = LONG_QUERY_TIMEOUT if "LIMIT" in query.upper() and "OFFSET" in query.upper() else QUERY_TIMEOUT
    
    async def execute_with_timeout():
        async with async_db_connection() as cursor:
            await cursor.execute(query, params)
            if fetch_all:
                return await cursor.fetchall()
            else:
                result = await cursor.fetchone()
                return [result] if result else None
    
    try:
        return await asyncio.wait_for(execute_with_timeout(), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"WARNING: Query timeout after {timeout} seconds")
        raise HTTPException(
            status_code=504, 
            detail=f"Query timeout after {timeout} seconds"
        )


# ==================== Prepared Statements ====================

# Common prepared statement patterns
PREPARED_STATEMENTS = {
    "liquidations_by_symbol_time": """
        SELECT symbol,
               FLOOR((order_trade_time - %s) / %s) * %s + %s AS start_timestamp,
               FLOOR((order_trade_time - %s) / %s) * %s + %s + %s AS end_timestamp,
               side,
               SUM(average_price * order_filled_accumulated_quantity) AS cumulated_usd_size
        FROM {table_name}
        WHERE LOWER(symbol) = %s
          AND order_trade_time BETWEEN %s AND %s
        GROUP BY symbol, start_timestamp, end_timestamp, side
    """,
    
    "symbols_distinct": """
        SELECT DISTINCT symbol
        FROM {table_name}
        WHERE symbol NOT REGEXP '[0-9]+$'
        ORDER BY symbol
    """,
    
    "orders_by_symbol_time_paginated": """
        SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
               average_price, order_status, order_last_filled_quantity, 
               order_filled_accumulated_quantity, order_trade_time
        FROM {table_name}
        WHERE LOWER(symbol) = %s AND order_trade_time BETWEEN %s AND %s
        ORDER BY order_trade_time DESC
        LIMIT %s OFFSET %s
    """,
    
    "orders_by_symbol_limit": """
        SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
               average_price, order_status, order_last_filled_quantity, 
               order_filled_accumulated_quantity, order_trade_time
        FROM {table_name}
        WHERE LOWER(symbol) = %s
        ORDER BY order_trade_time DESC
        LIMIT %s
    """,
    
    "orders_by_symbol_time_stream": """
        SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
               average_price, order_status, order_last_filled_quantity, 
               order_filled_accumulated_quantity, order_trade_time
        FROM {table_name}
        WHERE LOWER(symbol) = %s AND order_trade_time BETWEEN %s AND %s
        ORDER BY order_trade_time DESC
        LIMIT %s OFFSET %s
    """
}


async def async_execute_prepared_query(
    statement_name: str,
    params: Tuple = (),
    fetch_all: bool = True,
    timeout: Optional[int] = None
) -> Optional[List[Tuple[Any, ...]]]:
    """
    Execute a prepared statement with proper error handling and timeout.
    
    Args:
        statement_name: Name of the prepared statement from PREPARED_STATEMENTS
        params: Query parameters tuple
        fetch_all: If True, uses fetchall(), otherwise fetchone()
        timeout: Query timeout in seconds (uses default if None)
        
    Returns:
        Query results or None
    """
    if statement_name not in PREPARED_STATEMENTS:
        raise ValueError(f"Unknown prepared statement: {statement_name}")
    
    # Get table name from environment
    table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
    
    # Format the query with table name
    query = PREPARED_STATEMENTS[statement_name].format(table_name=table_name)
    
    # Execute using the standard async_execute_query
    return await async_execute_query(query, params, fetch_all, timeout)


# ==================== End Prepared Statements ====================

# ==================== End Async Database Utilities ====================


# ==================== FastAPI Dependency Alternative ====================

async def get_async_db_cursor() -> AsyncGenerator[aiomysql.Cursor, None]:
    """
    FastAPI dependency for async database cursor.
    
    This is an alternative to the context manager approach.
    FastAPI automatically handles the cleanup when using dependencies with yield.
    
    Yields:
        aiomysql.Cursor: Database cursor for executing queries
        
    Raises:
        HTTPException: If database connection fails
    """
    pool = await get_pool()
    conn = None
    cursor = None
    try:
        conn = await pool.acquire()
        cursor = await conn.cursor()
        yield cursor
    except Exception as err:
        print(f"ERROR: Database connection error: {err}")
        raise HTTPException(status_code=503, detail="Database service unavailable")
    finally:
        if cursor:
            await cursor.close()
        if conn:
            await pool.release(conn)


# ==================== End FastAPI Dependency Alternative ====================


# ==================== Application Lifecycle Events ====================

async def startup_event():
    """
    FastAPI startup event handler to initialize the database pool.
    """
    await initialize_pool()


async def shutdown_event():
    """
    FastAPI shutdown event handler to close the database pool.
    """
    await close_pool()


# ==================== End Application Lifecycle Events ====================