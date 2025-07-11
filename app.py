from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import mysql.connector
import os
import re
from functools import lru_cache, wraps
from contextlib import contextmanager
from typing import Generator, Optional, Any, List, Tuple, Callable

app = FastAPI()


# MySQL database configuration from environment variables
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_DATABASE"),
}

# Table name
table_name = os.getenv("DB_LIQ_TABLENAME")


# Cache for database connections
def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"FATAL: Could not connect to database: {err}")
        raise HTTPException(status_code=503, detail="Database service unavailable")


# ==================== Database Utilities ====================

@contextmanager
def db_connection() -> Generator[mysql.connector.cursor.MySQLCursor, None, None]:
    """
    Context manager for database connections with automatic cleanup.
    
    Yields:
        MySQLCursor: Database cursor for executing queries
        
    Raises:
        HTTPException: If database connection fails
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        yield cursor
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def db_error_handler(endpoint_name: str) -> Callable:
    """
    Decorator for consistent database error handling.
    
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
            except mysql.connector.Error as err:
                print(f"ERROR: Database error in {endpoint_name}: {err}")
                raise HTTPException(status_code=500, detail="Internal database error")
            except HTTPException:
                raise  # Re-raise HTTP exceptions as-is
            except Exception as e:
                print(f"ERROR: Unexpected error in {endpoint_name}: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        return wrapper
    return decorator


async def execute_query(
    query: str, 
    params: Tuple = (), 
    fetch_all: bool = True
) -> Optional[List[Tuple[Any, ...]]]:
    """
    Execute a database query with proper error handling.
    
    Args:
        query: SQL query string
        params: Query parameters tuple
        fetch_all: If True, uses fetchall(), otherwise fetchone()
        
    Returns:
        Query results or None
    """
    with db_connection() as cursor:
        cursor.execute(query, params)
        if fetch_all:
            return cursor.fetchall()
        else:
            result = cursor.fetchone()
            return [result] if result else None


# ==================== End Database Utilities ====================


# ==================== FastAPI Dependency Alternative ====================

from fastapi import Depends
from typing import Annotated

def get_db_cursor() -> Generator[mysql.connector.cursor.MySQLCursor, None, None]:
    """
    FastAPI dependency for database cursor.
    
    This is an alternative to the context manager approach.
    FastAPI automatically handles the cleanup when using dependencies with yield.
    
    Yields:
        MySQLCursor: Database cursor for executing queries
        
    Raises:
        HTTPException: If database connection fails
        
    Example usage in endpoint:
        @app.get("/api/example")
        async def example_endpoint(cursor: Annotated[mysql.connector.cursor.MySQLCursor, Depends(get_db_cursor)]):
            cursor.execute("SELECT * FROM table")
            return cursor.fetchall()
    
    Pros:
        - Integrates seamlessly with FastAPI's dependency injection
        - Automatic cleanup on both success and failure
        - Type hints work well with IDE support
        - Can be easily mocked in tests
        
    Cons:
        - Specific to FastAPI (not reusable in other contexts)
        - Requires understanding of FastAPI's dependency system
        - Slightly more verbose parameter definition
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        yield cursor
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# Example endpoint using dependency injection (commented out to avoid duplication)
# @app.get("/api/example-with-dependency")
# @db_error_handler("/api/example-with-dependency")
# async def example_with_dependency(
#     cursor: Annotated[mysql.connector.cursor.MySQLCursor, Depends(get_db_cursor)]
# ):
#     cursor.execute("SELECT COUNT(*) FROM binance_liqs")
#     count = cursor.fetchone()[0]
#     return {"total_records": count}

# ==================== End FastAPI Dependency Alternative ====================


def convert_timeframe_to_milliseconds(timeframe: str) -> int:
    timeframe = timeframe.lower()
    try:
        if timeframe.endswith("m"):
            return int(timeframe[:-1]) * 60 * 1000
        elif timeframe.endswith("h"):
            return int(timeframe[:-1]) * 3600 * 1000
        elif timeframe.endswith("d"):
            return int(timeframe[:-1]) * 86400 * 1000
        else:
            raise ValueError("Invalid timeframe format")
    except (ValueError, TypeError):
        raise ValueError("Invalid timeframe format")


def parse_timestamp(timestamp_str: str) -> int:
    """
    Parse a timestamp string to Unix milliseconds.
    
    Args:
        timestamp_str: Either a Unix timestamp in milliseconds or an ISO format datetime string
        
    Returns:
        Unix timestamp in milliseconds
        
    Raises:
        ValueError: If the timestamp string cannot be parsed
    """
    try:
        # Try to parse as integer first (handles both positive and negative numbers)
        return int(timestamp_str)
    except ValueError:
        # If that fails, try as ISO format
        try:
            return int(datetime.fromisoformat(timestamp_str).timestamp() * 1000)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid timestamp format: {timestamp_str}") from e


class LiquidationRequest(BaseModel):
    symbol: str
    timeframe: str
    start_timestamp_iso: str
    end_timestamp_iso: str


@app.get("/api/liquidations")
@db_error_handler("/api/liquidations")
async def get_liquidations(
    symbol: str = Query(..., description="Symbol to filter by"),
    timeframe: str = Query(..., description="Timeframe for aggregation"),
    start_timestamp: str = Query(
        ..., description="Start timestamp in ISO or Unix format"
    ),
    end_timestamp: str = Query(..., description="End timestamp in ISO or Unix format"),
):
    table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
    
    # Parameter validation
    try:
        start_timestamp = parse_timestamp(start_timestamp)
        end_timestamp = parse_timestamp(end_timestamp)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="start_timestamp and end_timestamp must be valid Unix timestamps in miliseconds or datetime strings in ISO format",
        )

    timeframe_milliseconds = convert_timeframe_to_milliseconds(timeframe)
    if start_timestamp < 0 or end_timestamp < 0:
        raise HTTPException(
            status_code=400,
            detail="start_timestamp and end_timestamp must be non-negative integers",
        )

    if start_timestamp > end_timestamp:
        raise HTTPException(
            status_code=400, detail="start_timestamp must be before end_timestamp"
        )

    # Database query
    query = f"""
    SELECT symbol,
           FLOOR((order_trade_time - %s) / %s) * %s + %s AS start_timestamp,
           FLOOR((order_trade_time - %s) / %s) * %s + %s + %s AS end_timestamp,
           side,
           SUM(usd_size) AS cumulated_usd_size
    FROM {table_name}
    WHERE LOWER(symbol) = %s
      AND order_trade_time BETWEEN %s AND %s
    GROUP BY symbol, start_timestamp, end_timestamp, side;
    """
    
    params = (
        start_timestamp,
        timeframe_milliseconds,
        timeframe_milliseconds,
        start_timestamp,
        start_timestamp,
        timeframe_milliseconds,
        timeframe_milliseconds,
        start_timestamp,
        timeframe_milliseconds,
        symbol.lower(),
        start_timestamp,
        end_timestamp,
    )
    
    db_results = await execute_query(query, params)
    
    if not db_results:
        raise HTTPException(
            status_code=404, detail="No data found for the given parameters"
        )
    
    # Format results
    results = [
        {
            "timestamp": result[1],
            "timestamp_iso": datetime.fromtimestamp(
                int(result[1]) / 1000, tz=timezone.utc
            ).isoformat(),
            "side": result[3],
            "cumulated_usd_size": float(result[4]),
        }
        for result in db_results
    ]
    
    return results


@app.get("/api/symbols")
@db_error_handler("/api/symbols")
async def get_symbols():
    query = """
    SELECT DISTINCT symbol
    FROM {}
    WHERE symbol NOT REGEXP '[0-9]+$'
    ORDER BY symbol
    """.format(table_name)
    
    results = await execute_query(query, ())
    symbols = [result[0] for result in results]
    
    return symbols


@app.get("/api/liquidation-orders")
@db_error_handler("/api/liquidation-orders")
async def get_liquidation_orders(
    symbol: str = Query(..., description="Trading symbol to filter by"),
    start_timestamp: str = Query(None, description="Start timestamp in ISO or Unix format"),
    end_timestamp: str = Query(None, description="End timestamp in ISO or Unix format"),
    limit: int = Query(None, description="Number of orders to return", gt=0, le=1000),
):
    """
    Get liquidation orders for a specific symbol.
    
    Either provide both start_timestamp and end_timestamp, or provide limit.
    Cannot provide both timestamp range and limit.
    """
    table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
    
    # Complex parameter validation
    has_timestamps = start_timestamp is not None and end_timestamp is not None
    has_single_timestamp = (start_timestamp is not None) != (end_timestamp is not None)
    has_limit = limit is not None
    
    if has_single_timestamp:
        raise HTTPException(
            status_code=400,
            detail="Both start_timestamp and end_timestamp must be provided together"
        )
    
    if has_timestamps and has_limit:
        raise HTTPException(
            status_code=400,
            detail="Cannot provide both timestamp range and limit"
        )
    
    if not has_timestamps and not has_limit:
        raise HTTPException(
            status_code=400,
            detail="Either provide both timestamps or a limit parameter"
        )
    
    # Parse timestamps if provided
    if has_timestamps:
        try:
            start_ts = parse_timestamp(start_timestamp)
            end_ts = parse_timestamp(end_timestamp)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid timestamp format. Use Unix milliseconds or ISO format"
            )
        
        if start_ts < 0 or end_ts < 0:
            raise HTTPException(
                status_code=400,
                detail="Timestamps must be non-negative"
            )
        
        if start_ts > end_ts:
            raise HTTPException(
                status_code=400,
                detail="start_timestamp must be before end_timestamp"
            )
    
    # Build query based on parameters
    if has_timestamps:
        # Query with timestamp range
        query = f"""
        SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
               average_price, order_status, order_last_filled_quantity, 
               order_filled_accumulated_quantity, order_trade_time
        FROM {table_name}
        WHERE LOWER(symbol) = %s AND order_trade_time BETWEEN %s AND %s
        ORDER BY order_trade_time DESC
        """
        params = (symbol.lower(), start_ts, end_ts)
    else:
        # Query with limit
        query = f"""
        SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
               average_price, order_status, order_last_filled_quantity, 
               order_filled_accumulated_quantity, order_trade_time
        FROM {table_name}
        WHERE LOWER(symbol) = %s
        ORDER BY order_trade_time DESC
        LIMIT %s
        """
        params = (symbol.lower(), limit)
    
    # Execute query
    results = await execute_query(query, params)
    
    if not results:
        raise HTTPException(
            status_code=404,
            detail="No liquidation orders found for the given criteria"
        )
    
    # Format results
    orders = []
    for row in results:
        orders.append({
            "symbol": row[0],
            "side": row[1],
            "order_type": row[2],
            "time_in_force": row[3],
            "original_quantity": float(row[4]) if row[4] is not None else None,
            "price": float(row[5]) if row[5] is not None else None,
            "average_price": float(row[6]) if row[6] is not None else None,
            "order_status": row[7],
            "order_last_filled_quantity": float(row[8]) if row[8] is not None else None,
            "order_filled_accumulated_quantity": float(row[9]) if row[9] is not None else None,
            "order_trade_time": row[10]
        })
    
    return orders