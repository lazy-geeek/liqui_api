from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime, timezone
import mysql.connector
import os
import json
from functools import wraps
from contextlib import contextmanager
from typing import Generator, Optional, Any, List, Tuple, Callable

# Import async database utilities
from app_async_db import (
    async_execute_query,
    async_db_error_handler,
    startup_event as db_startup_event,
    shutdown_event as db_shutdown_event
)

# Import cache utilities
from cache_config import (
    cache_startup_event,
    cache_shutdown_event,
    cache_result,
    get_cache_stats,
    clear_cache_by_pattern,
    invalidate_cache_for_symbol,
    invalidate_symbols_cache,
    warm_all_caches
)

app = FastAPI()

# Add middleware for response compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add lifecycle events for async database pool and cache
async def app_startup():
    await db_startup_event()
    await cache_startup_event()
    # Warm the cache with popular queries (non-blocking)
    import asyncio
    asyncio.create_task(warm_all_caches())

async def app_shutdown():
    await cache_shutdown_event()
    await db_shutdown_event()

app.add_event_handler("startup", app_startup)
app.add_event_handler("shutdown", app_shutdown)


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
def db_connection() -> Generator[Any, None, None]:
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

def get_db_cursor() -> Generator[Any, None, None]:
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
        async def example_endpoint(cursor: Annotated[Any, Depends(get_db_cursor)]):
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
#     cursor: Annotated[Any, Depends(get_db_cursor)]
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
@async_db_error_handler("/api/liquidations")
@cache_result("liquidations")
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
        start_timestamp_ms = parse_timestamp(start_timestamp)
        end_timestamp_ms = parse_timestamp(end_timestamp)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="start_timestamp and end_timestamp must be valid Unix timestamps in miliseconds or datetime strings in ISO format",
        )

    timeframe_milliseconds = convert_timeframe_to_milliseconds(timeframe)
    if start_timestamp_ms < 0 or end_timestamp_ms < 0:
        raise HTTPException(
            status_code=400,
            detail="start_timestamp and end_timestamp must be non-negative integers",
        )

    if start_timestamp_ms > end_timestamp_ms:
        raise HTTPException(
            status_code=400, detail="start_timestamp must be before end_timestamp"
        )

    # Database query
    query = f"""
    SELECT symbol,
           FLOOR((order_trade_time - %s) / %s) * %s + %s AS start_timestamp,
           FLOOR((order_trade_time - %s) / %s) * %s + %s + %s AS end_timestamp,
           side,
           SUM(average_price * order_filled_accumulated_quantity) AS cumulated_usd_size
    FROM {table_name}
    WHERE LOWER(symbol) = %s
      AND order_trade_time BETWEEN %s AND %s
    GROUP BY symbol, start_timestamp, end_timestamp, side;
    """
    
    params = (
        start_timestamp_ms,
        timeframe_milliseconds,
        timeframe_milliseconds,
        start_timestamp_ms,
        start_timestamp_ms,
        timeframe_milliseconds,
        timeframe_milliseconds,
        start_timestamp_ms,
        timeframe_milliseconds,
        symbol.lower(),
        start_timestamp_ms,
        end_timestamp_ms,
    )
    
    db_results = await async_execute_query(query, params)
    
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
@async_db_error_handler("/api/symbols")
@cache_result("symbols")
async def get_symbols():
    query = """
    SELECT DISTINCT symbol
    FROM {}
    WHERE symbol NOT REGEXP '[0-9]+$'
    ORDER BY symbol
    """.format(table_name)
    
    results = await async_execute_query(query, ())
    if not results:
        return []
    
    symbols = [result[0] for result in results]
    
    return symbols


@app.get("/api/liquidation-orders")
@async_db_error_handler("/api/liquidation-orders")
@cache_result("orders")
async def get_liquidation_orders(
    symbol: str = Query(..., description="Trading symbol to filter by"),
    start_timestamp: str = Query(None, description="Start timestamp in ISO or Unix format"),
    end_timestamp: str = Query(None, description="End timestamp in ISO or Unix format"),
    limit: int = Query(None, description="Number of orders to return", gt=0, le=1000),
    page: int = Query(1, description="Page number for pagination", gt=0),
    page_size: int = Query(100, description="Number of results per page", gt=0, le=1000),
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
    
    # Handle pagination - limit takes precedence over pagination
    if has_limit:
        # When limit is provided, ignore pagination parameters
        actual_limit = limit
        offset = 0
    else:
        # When using timestamp range, apply pagination
        actual_limit = page_size
        offset = (page - 1) * page_size
    
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
        # Query with timestamp range and pagination
        query = f"""
        SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
               average_price, order_status, order_last_filled_quantity, 
               order_filled_accumulated_quantity, order_trade_time
        FROM {table_name}
        WHERE LOWER(symbol) = %s AND order_trade_time BETWEEN %s AND %s
        ORDER BY order_trade_time DESC
        LIMIT %s OFFSET %s
        """
        params = (symbol.lower(), start_ts, end_ts, actual_limit, offset)
    else:
        # Query with limit (no pagination when using limit parameter)
        query = f"""
        SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
               average_price, order_status, order_last_filled_quantity, 
               order_filled_accumulated_quantity, order_trade_time
        FROM {table_name}
        WHERE LOWER(symbol) = %s
        ORDER BY order_trade_time DESC
        LIMIT %s
        """
        params = (symbol.lower(), actual_limit)
    
    # Execute query
    results = await async_execute_query(query, params)
    
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
    
    # Add pagination metadata when using timestamp range with pagination
    if has_timestamps and not has_limit:
        return {
            "data": orders,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_returned": len(orders),
                "has_more": len(orders) == page_size  # Indicates if there might be more pages
            }
        }
    else:
        # Return simple array for backward compatibility when using limit
        return orders


@app.get("/api/liquidation-orders/stream")
@async_db_error_handler("/api/liquidation-orders/stream")
async def stream_liquidation_orders(
    symbol: str = Query(..., description="Trading symbol to filter by"),
    start_timestamp: str = Query(..., description="Start timestamp in ISO or Unix format"),
    end_timestamp: str = Query(..., description="End timestamp in ISO or Unix format"),
    batch_size: int = Query(1000, description="Number of records per batch", gt=0, le=5000),
):
    """
    Stream liquidation orders for very large result sets.
    Returns data in JSONL format (one JSON object per line).
    """
    table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
    
    # Parse timestamps
    try:
        start_ts = parse_timestamp(start_timestamp)
        end_ts = parse_timestamp(end_timestamp)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid timestamp format. Use Unix milliseconds or ISO format"
        )
    
    if start_ts > end_ts:
        raise HTTPException(
            status_code=400,
            detail="start_timestamp must be before end_timestamp"
        )
    
    async def generate_stream():
        """Generator function to stream results in batches."""
        try:
            offset = 0
            while True:
                # Query with batch size and offset
                query = f"""
                SELECT symbol, side, order_type, time_in_force, original_quantity, price, 
                       average_price, order_status, order_last_filled_quantity, 
                       order_filled_accumulated_quantity, order_trade_time
                FROM {table_name}
                WHERE LOWER(symbol) = %s AND order_trade_time BETWEEN %s AND %s
                ORDER BY order_trade_time DESC
                LIMIT %s OFFSET %s
                """
                params = (symbol.lower(), start_ts, end_ts, batch_size, offset)
                
                # Execute query
                results = await async_execute_query(query, params)
                
                if not results:
                    break  # No more results
                
                # Stream each record as a JSON line
                for row in results:
                    order = {
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
                    }
                    yield json.dumps(order) + "\n"
                
                # If we got fewer results than batch_size, we're done
                if len(results) < batch_size:
                    break
                
                offset += batch_size
                
        except Exception as e:
            # Stream an error message
            error_msg = {"error": f"Streaming error: {str(e)}"}
            yield json.dumps(error_msg) + "\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f"attachment; filename=liquidation_orders_{symbol}_{start_timestamp}_{end_timestamp}.jsonl"
        }
    )


# ==================== Cache Management Endpoints ====================

@app.get("/api/cache/stats")
async def get_cache_statistics():
    """
    Get cache statistics including hit rate, memory usage, and connection info.
    """
    stats = await get_cache_stats()
    return {
        "cache_stats": stats,
        "message": "Cache statistics retrieved successfully" if stats.get("available") else "Cache not available"
    }


@app.post("/api/cache/clear")
async def clear_cache(pattern: str = "*"):
    """
    Clear cache entries matching a pattern.
    
    Args:
        pattern: Redis pattern (default: "*" for all keys)
    """
    try:
        deleted_count = await clear_cache_by_pattern(pattern)
        return {
            "deleted_keys": deleted_count,
            "pattern": pattern,
            "message": f"Successfully cleared {deleted_count} cache entries"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@app.post("/api/cache/invalidate/symbol/{symbol}")
async def invalidate_symbol_cache(symbol: str):
    """
    Invalidate all cache entries for a specific symbol.
    
    Args:
        symbol: Trading symbol to invalidate
    """
    try:
        deleted_count = await invalidate_cache_for_symbol(symbol)
        return {
            "deleted_keys": deleted_count,
            "symbol": symbol,
            "message": f"Successfully invalidated {deleted_count} cache entries for symbol {symbol}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache invalidation failed: {str(e)}")


@app.post("/api/cache/invalidate/symbols")
async def invalidate_symbols_endpoint():
    """
    Invalidate the symbols cache.
    """
    try:
        success = await invalidate_symbols_cache()
        return {
            "success": success,
            "message": "Symbols cache invalidated successfully" if success else "Failed to invalidate symbols cache"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Symbols cache invalidation failed: {str(e)}")


@app.post("/api/cache/warm")
async def warm_cache_endpoint():
    """
    Manually warm the cache with popular queries.
    """
    try:
        import asyncio
        # Run cache warming in background
        task = asyncio.create_task(warm_all_caches())
        return {
            "message": "Cache warming started in background",
            "status": "initiated"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache warming failed: {str(e)}")


# ==================== End Cache Management Endpoints ====================


# ==================== Health Check Endpoint ====================

@app.get("/health")
async def health_check():
    """
    Health check endpoint for deployment monitoring.
    Checks database connectivity and Redis availability.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {}
    }
    
    overall_healthy = True
    
    # Check database connectivity
    try:
        # Simple query to check database connectivity
        result = await async_execute_query("SELECT 1", (), fetch_all=False)
        if result:
            health_status["components"]["database"] = {
                "status": "healthy",
                "message": "Database connection successful"
            }
        else:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "message": "Database query returned no results"
            }
            overall_healthy = False
    except Exception as e:
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
        overall_healthy = False
    
    # Check Redis connectivity
    try:
        cache_stats = await get_cache_stats()
        if cache_stats.get("available"):
            health_status["components"]["redis"] = {
                "status": "healthy",
                "message": "Redis connection successful",
                "hit_rate": cache_stats.get("hit_rate", 0)
            }
        else:
            health_status["components"]["redis"] = {
                "status": "degraded",
                "message": "Redis not available - running in fallback mode"
            }
            # Redis being down is not critical, just degraded performance
    except Exception as e:
        health_status["components"]["redis"] = {
            "status": "degraded",
            "message": f"Redis check failed: {str(e)}"
        }
        # Redis being down is not critical, just degraded performance
    
    # Set overall status
    if not overall_healthy:
        health_status["status"] = "unhealthy"
        return health_status, 503
    
    return health_status

# ==================== End Health Check Endpoint ====================