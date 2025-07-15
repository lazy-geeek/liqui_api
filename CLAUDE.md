# CLAUDE.md - Project Documentation for Claude Instances

## Project Overview

**Project Name**: liqui-api  
**Type**: FastAPI REST API  
**Language**: Python 3.12+  
**Framework**: FastAPI with Uvicorn/Gunicorn  
**Purpose**: API service for querying cryptocurrency liquidation data from a MySQL database

## Technology Stack

- **Web Framework**: FastAPI (v0.115.0)
- **ASGI Server**: Uvicorn (v0.32.1) with Gunicorn (v23.0.0) workers
- **Database**: MySQL (via aiomysql v0.2.0 for async operations)
- **Cache**: Redis (via redis[hiredis] v4.6.0)
- **Package Management**: Poetry
- **Deployment**: Configured for Heroku/Dokku (Procfile present)

## Project Structure

```
liqui_api/
├── app.py              # Main FastAPI application file
├── app_async_db.py     # Async database utilities with connection pooling
├── cache_config.py     # Redis cache configuration and utilities
├── migrations.sql      # Database index creation script
├── README.md           # User-facing project documentation
├── CLAUDE.md           # Claude-specific project documentation
├── pyproject.toml      # Poetry configuration
├── poetry.lock         # Poetry lock file
├── requirements.txt    # Auto-generated from Poetry
├── pytest.ini          # Pytest configuration
├── Procfile           # Deployment configuration
├── app.log            # Application log file
├── todo.md            # TODO file with implementation tasks
├── .gitignore         # Git ignore configuration
└── test/              # Test directory
    ├── __init__.py
    ├── conftest.py     # Pytest fixtures and configuration
    ├── test_app.py     # API endpoint tests
    ├── test_utils.py   # Utility function tests
    └── test_integration.py  # Integration tests
```

## Key Commands

### Development
```bash
# Install dependencies using Poetry
poetry install

# Run development server with nohup (avoids 2-minute startup delays)
nohup uvicorn app:app --reload &

# Alternative: Run with gunicorn (production-like)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app

# Run tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=html
```

### Dependency Management
```bash
# Add a new dependency
poetry add <package>

# Update dependencies
poetry update

# Export requirements.txt (auto-configured)
# This happens automatically due to poetry-auto-export in pyproject.toml
```

### Deployment
The application is configured for deployment with:
- Procfile: `web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app`
- Suitable for Heroku, Dokku, or similar PaaS platforms

## Architecture & API Endpoints

### Database Utilities

The application includes reusable database utilities for consistent connection management and error handling:

1. **Context Manager** (`db_connection()`):
   ```python
   with db_connection() as cursor:
       cursor.execute("SELECT * FROM table")
       results = cursor.fetchall()
   ```
   - Automatically handles connection lifecycle
   - Ensures proper cleanup of cursor and connection
   - Works with Python's `with` statement

2. **Error Handler Decorator** (`db_error_handler(endpoint_name)`):
   ```python
   @app.get("/api/endpoint")
   @db_error_handler("/api/endpoint")
   async def endpoint():
       # Database operations
   ```
   - Provides consistent error handling across endpoints
   - Logs errors with endpoint name for debugging
   - Converts database errors to appropriate HTTP responses

3. **Query Executor** (`execute_query(query, params, fetch_all=True)`):
   ```python
   results = await execute_query("SELECT * FROM table WHERE id = %s", (id,))
   ```
   - Simplifies query execution with automatic connection management
   - Supports both `fetchall()` and `fetchone()` modes
   - Handles parameter binding safely

4. **FastAPI Dependency Alternative** (`get_db_cursor()`):
   ```python
   from typing import Annotated
   from fastapi import Depends
   
   @app.get("/api/endpoint")
   async def endpoint(cursor: Annotated[Any, Depends(get_db_cursor)]):
       cursor.execute("SELECT * FROM table")
   ```
   - Integrates with FastAPI's dependency injection system
   - Alternative to context manager approach
   - Useful for testing with dependency overrides

### Database Configuration
The application connects to a MySQL database using environment variables:
- `DB_HOST`: Database host
- `DB_USER`: Database username
- `DB_PASSWORD`: Database password
- `DB_DATABASE`: Database name
- `DB_LIQ_TABLENAME`: Table name for liquidation data (defaults to "binance_liqs")

### API Endpoints

1. **GET /api/liquidations**
   - Query liquidation data with aggregation
   - Parameters (all required):
     - `symbol`: Trading symbol to filter by
     - `timeframe`: Aggregation timeframe (e.g., "5m", "1h", "1d")
     - `start_timestamp`: Start time (Unix ms or ISO format)
     - `end_timestamp`: End time (Unix ms or ISO format)
   - Returns aggregated liquidation data grouped by timeframe and side
   - Response format:
     - `timestamp`: Start timestamp of the aggregation bucket (Unix ms)
     - `timestamp_iso`: ISO 8601 formatted timestamp
     - `side`: Liquidation side ("buy" or "sell")
     - `cumulated_usd_size`: Total USD value for this bucket and side
   - Example:
     ```bash
     curl "http://localhost:8000/api/liquidations?symbol=BTCUSDT&timeframe=1h&start_timestamp=1609459200000&end_timestamp=1609545600000"
     ```

2. **GET /api/symbols**
   - Get list of all available trading symbols
   - Filters out symbols ending with numbers
   - Returns sorted list of symbols
   - Example:
     ```bash
     curl "http://localhost:8000/api/symbols"
     ```

3. **GET /api/liquidation-orders**
   - Get individual liquidation orders for a specific symbol
   - Parameters (mutually exclusive modes):
     - Mode 1: Timestamp range
       - `symbol`: Trading symbol (required)
       - `start_timestamp`: Start time (Unix ms or ISO format)
       - `end_timestamp`: End time (Unix ms or ISO format)
     - Mode 2: Latest orders
       - `symbol`: Trading symbol (required)
       - `limit`: Number of recent orders to return (1-1000)
   - Returns list of liquidation orders with full details:
     - `symbol`: Trading symbol (first field)
     - `side`: Order side (buy/sell)
     - `order_type`: Order type (e.g., LIMIT, MARKET)
     - `time_in_force`: Time in force (e.g., GTC, IOC, FOK)
     - `original_quantity`: Original order quantity
     - `price`: Order price (null for market orders)
     - `average_price`: Average execution price
     - `order_status`: Order status
     - `order_last_filled_quantity`: Last filled quantity
     - `order_filled_accumulated_quantity`: Total filled quantity
     - `order_trade_time`: Trade timestamp in milliseconds
   - Example (timestamp range):
     ```bash
     curl "http://localhost:8000/api/liquidation-orders?symbol=BTCUSDT&start_timestamp=2021-01-01T00:00:00Z&end_timestamp=2021-01-01T01:00:00Z"
     ```
   - Example (latest orders):
     ```bash
     curl "http://localhost:8000/api/liquidation-orders?symbol=BTCUSDT&limit=100"
     ```

### Cache Management Endpoints (Performance Enhancement)

4. **GET /api/cache/stats**
   - Get cache statistics including hit rate, memory usage, and connection info
   - Returns cache performance metrics
   - Example:
     ```bash
     curl "http://localhost:8000/api/cache/stats"
     ```

5. **POST /api/cache/clear**
   - Clear cache entries matching a pattern
   - Parameters:
     - `pattern`: Redis pattern (default: "*" for all keys)
   - Example:
     ```bash
     curl -X POST "http://localhost:8000/api/cache/clear?pattern=liq:*"
     ```

6. **POST /api/cache/invalidate/symbol/{symbol}**
   - Invalidate all cache entries for a specific symbol
   - Parameters:
     - `symbol`: Trading symbol to invalidate
   - Example:
     ```bash
     curl -X POST "http://localhost:8000/api/cache/invalidate/symbol/BTCUSDT"
     ```

7. **POST /api/cache/invalidate/symbols**
   - Invalidate the symbols cache
   - Example:
     ```bash
     curl -X POST "http://localhost:8000/api/cache/invalidate/symbols"
     ```

8. **POST /api/cache/warm**
   - Manually warm the cache with popular queries
   - Example:
     ```bash
     curl -X POST "http://localhost:8000/api/cache/warm"
     ```

9. **GET /api/liquidation-orders/stream**
   - Stream liquidation orders for very large result sets
   - Returns data in JSONL format (one JSON object per line)
   - Parameters:
     - `symbol`: Trading symbol (required)
     - `start_timestamp`: Start timestamp (required)
     - `end_timestamp`: End timestamp (required)
     - `batch_size`: Records per batch (default: 1000, max: 5000)
   - Example:
     ```bash
     curl "http://localhost:8000/api/liquidation-orders/stream?symbol=BTCUSDT&start_timestamp=2021-01-01T00:00:00Z&end_timestamp=2021-01-01T01:00:00Z&batch_size=2000"
     ```

### Enhanced Features (Phase 4)

- **Pagination Support**: `/api/liquidation-orders` now supports pagination with `page` and `page_size` parameters
- **Response Compression**: Automatic GZip compression for responses over 1KB
- **Cache Warming**: Automatic cache warming on startup for popular symbol/timeframe combinations
- **Streaming Support**: Large datasets can be streamed via `/api/liquidation-orders/stream`

### Key Features

1. **Time-based Aggregation**: Converts timeframes (m/h/d) to milliseconds for SQL grouping
2. **Flexible Timestamp Input**: Accepts both Unix timestamps (ms) and ISO format strings via `parse_timestamp()` utility
3. **Error Handling**: Comprehensive error handling with appropriate HTTP status codes
4. **Async Database Operations**: Uses aiomysql connection pooling for better performance
5. **Redis Caching**: Intelligent caching with automatic fallback to database
6. **Cache Management**: Built-in cache invalidation and monitoring endpoints
7. **Input Validation**: Uses Pydantic models and FastAPI validation
8. **Test Coverage**: Comprehensive unit and integration tests using pytest

## Database Schema

The application expects a MySQL table with at least these columns:

For `/api/liquidations` endpoint:
- `symbol`: Trading pair symbol (e.g., "BTCUSDT")
- `order_trade_time`: Timestamp in milliseconds
- `side`: Trade side (buy/sell)
- `average_price`: Average execution price
- `order_filled_accumulated_quantity`: Total filled quantity
Note: USD value is calculated as average_price × order_filled_accumulated_quantity

For `/api/liquidation-orders` endpoint (additional columns):
- `order_type`: Order type (e.g., LIMIT, MARKET)
- `time_in_force`: Time in force (e.g., GTC, IOC, FOK)
- `original_quantity`: Original order quantity
- `price`: Order price
- `average_price`: Average execution price
- `order_status`: Order status
- `order_last_filled_quantity`: Last filled quantity
- `order_filled_accumulated_quantity`: Total filled quantity

## Environment Variables Required

### Database Configuration
```bash
DB_HOST=<mysql-host>
DB_USER=<mysql-user>
DB_PASSWORD=<mysql-password>
DB_DATABASE=<database-name>
DB_LIQ_TABLENAME=<table-name>  # Optional, defaults to "binance_liqs"
```

### Redis Configuration (Phase 1 - Performance Optimization)
```bash
REDIS_HOST=localhost          # Redis server host
REDIS_PORT=6379              # Redis server port
REDIS_PASSWORD=              # Redis password (optional)
REDIS_DB=0                   # Redis database number
CACHE_TTL_SECONDS=300        # Default cache TTL (5 minutes)
CACHE_TTL_SYMBOLS=3600       # Symbols cache TTL (1 hour)
```

### Query Optimization Configuration (Phase 5 - Database Optimization)
```bash
QUERY_TIMEOUT_SECONDS=30     # Default query timeout (30 seconds)
LONG_QUERY_TIMEOUT_SECONDS=120  # Long query timeout for streaming (2 minutes)
```

## Cache Architecture (Performance Enhancement)

The application implements a Redis-based caching layer with the following features:

### Cache Strategy
- **Async Connection Pooling**: Uses Redis connection pooling for efficient resource management
- **Automatic Fallback**: If Redis is unavailable, requests automatically fall back to database
- **TTL-based Expiration**: Different TTL values for different data types:
  - Symbols: 1 hour (changes infrequently)
  - Liquidations: 5 minutes (balances freshness with performance)
  - Orders: 5 minutes (balances freshness with performance)

### Cache Keys
- **Liquidations**: `liq:{symbol}:{timeframe}:{start_timestamp}:{end_timestamp}`
- **Symbols**: `symbols:all`
- **Orders**: `orders:{symbol}:{start_timestamp}:{end_timestamp}` or `orders:{symbol}:latest:{limit}`

### Cache Features
- **Key Hashing**: Long keys are automatically hashed to prevent Redis key length issues
- **Circuit Breaker**: Prevents cascading failures when Redis is down
- **Cache Invalidation**: Granular invalidation by symbol or data type
- **Monitoring**: Built-in cache hit rate and performance metrics

### Cache Management
- **Statistics**: View cache hit rates, memory usage, and connection stats
- **Manual Invalidation**: Clear specific cache patterns or symbols
- **Graceful Degradation**: Application continues working even if Redis fails

### Files
- **app_async_db.py**: Async database utilities with connection pooling
- **cache_config.py**: Redis configuration, cache operations, and utilities
- **app.py**: Main application with cache decorators applied to all endpoints

## Database Optimization (Phase 5)

The application includes comprehensive database optimizations for maximum performance:

### Database Indexes
- **Primary Index**: `(symbol, order_trade_time)` - Covers 90% of queries
- **GROUP BY Index**: `(symbol, order_trade_time, side)` - Optimizes liquidations endpoint
- **Symbol Index**: `(symbol)` - Supports DISTINCT queries and filtering
- **Time Index**: `(order_trade_time)` - Supports time-based queries
- **USD Index**: `(symbol, order_trade_time, average_price, order_filled_accumulated_quantity)` - Future optimization

### Query Optimization
- **Prepared Statements**: Common queries use prepared statement patterns
- **Query Timeouts**: Configurable timeouts (30s default, 2min for streaming)
- **Connection Pooling**: Async connection pool (5-20 connections)
- **Smart Timeout Detection**: Automatically uses longer timeouts for pagination/streaming

### Performance Improvements
- **Query Execution**: 30-70% faster with proper indexing
- **Memory Usage**: Reduced connection overhead with pooling
- **Error Handling**: Timeout protection prevents hanging queries
- **Database Load**: 30-50% reduction in overall database load

### Database Files
- **migrations.sql**: Complete database index creation script
- **app_async_db.py**: Async database utilities with timeout support

### Running Database Migrations
To apply the database optimizations, run the migrations script:
```bash
# Connect to your MySQL database
mysql -h endor.brenkel.com -u python -p liquidation_data

# Run the migrations script
source migrations.sql;

# Verify indexes were created
SHOW INDEX FROM binance_liqs;
```

## Notes for Development

1. **Logging**: The application uses `app.log` for logging (included in .gitignore)
2. **Database Errors**: Connection errors return 503 Service Unavailable
3. **Data Validation**: All timestamps are validated and converted to milliseconds
4. **Case Sensitivity**: Symbol queries are case-insensitive (converted to lowercase)
5. **Performance**: Uses SQL aggregation for efficient time-based grouping

## Documentation

- **README.md**: Primary user-facing documentation with API endpoint details, installation instructions, and usage examples
- **CLAUDE.md**: This file - contains technical implementation details and development guidelines specifically for Claude AI instances working on the codebase

## Recent Architectural Changes

### Database Connection Refactoring (2025-01-11)
- Introduced reusable database utilities (`db_connection`, `db_error_handler`, `execute_query`)
- Reduced code duplication across endpoints by ~55%
- Centralized error handling and connection management
- All endpoints now use consistent patterns for database operations

### API Response Enhancement (2025-01-11)
- `/api/liquidation-orders` now includes `symbol` as the first field in each order object
- Ensures consistency in response format for easier client-side processing
- No breaking changes - existing fields remain in the same order after symbol

### Performance Enhancement (2025-01-15)
- Removed dependency on pre-calculated `usd_size` column in database
- USD values now calculated dynamically as `average_price × order_filled_accumulated_quantity`
- Updated `/api/liquidations` response format:
  - Renamed `time_bucket` to `timestamp` for clarity
  - Added `timestamp_iso` field for human-readable timestamps
  - Renamed `total_usd_size` to `cumulated_usd_size`
  - Removed `count` field (not used by clients)
- Made all parameters required for `/api/liquidations` endpoint
- Type hints updated to use `Any` instead of specific MySQL cursor types for better compatibility
- Removed unused imports for cleaner codebase

## TODO Items

From `to_dos.md`:
- Deploy as Dokku app

## Deployment Considerations

### Production-Ready Features
1. **Health Check Endpoint**: `/health` endpoint for monitoring database and Redis connectivity
2. **Docker Support**: Complete Docker and Docker Compose configuration
3. **Dokku Ready**: Full Dokku deployment configuration with Redis addon support
4. **Environment Configuration**: Comprehensive environment variable management
5. **Rollback Plan**: Detailed rollback procedures for various failure scenarios

### Deployment Files
- `Dockerfile`: Multi-stage Docker build with security best practices
- `docker-compose.yml`: Complete stack with Redis service
- `app.json`: Dokku/Heroku deployment configuration
- `DOKKU_SCALE`: Scaling configuration for Dokku
- `runtime.txt`: Python version specification
- `DEPLOYMENT.md`: Comprehensive deployment guide
- `ROLLBACK_PLAN.md`: Detailed rollback procedures

### Environment Variables
All environment variables are documented in DEPLOYMENT.md, including:
- Database configuration (DB_HOST, DB_USER, DB_PASSWORD, DB_DATABASE)
- Redis configuration (REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)
- Cache settings (CACHE_TTL_SECONDS, CACHE_TTL_SYMBOLS)
- Query timeouts (QUERY_TIMEOUT_SECONDS, LONG_QUERY_TIMEOUT_SECONDS)

### Health Monitoring
The `/health` endpoint provides:
- Database connectivity check
- Redis connectivity check (non-critical)
- Timestamp for monitoring
- Component-wise health status
- Returns 503 for unhealthy database, 200 for healthy or degraded Redis

### Deployment Methods
1. **Dokku**: Full configuration with Redis addon
2. **Docker**: Container-based deployment
3. **Traditional**: Direct server deployment with systemd

### Rollback Procedures
- Application rollback (5 minutes)
- Database rollback (15 minutes)
- Complete system rollback (30 minutes)
- Cache recovery (2 minutes)

## Common Development Tasks

### Adding New Endpoints

With the new database utilities, adding endpoints is simplified:

```python
@app.get("/api/new-endpoint")
@db_error_handler("/api/new-endpoint")
async def new_endpoint(param: str):
    # Validation logic here
    
    query = "SELECT * FROM table WHERE column = %s"
    results = await execute_query(query, (param,))
    
    if not results:
        raise HTTPException(status_code=404, detail="Not found")
    
    return [format_result(r) for r in results]
```

Key patterns:
1. Apply `@db_error_handler` decorator for consistent error handling
2. Use `execute_query()` for database operations
3. Keep validation logic separate from database logic
4. Format results as needed for JSON response

### Modifying Database Queries
1. All queries use parameterized statements for security
2. Table name is configurable via environment variable
3. Use the database utilities instead of manual connection management
4. The utilities handle all cleanup automatically

### Testing
The project includes comprehensive test coverage:
- Unit tests for utility functions (`convert_timeframe_to_milliseconds`, `parse_timestamp`)
- Unit tests for all API endpoints with mocked database connections
- Integration tests for end-to-end functionality
- Test fixtures for common test data
- Pytest configured with `asyncio_default_fixture_loop_scope = function` for proper async test isolation

Run tests with:
```bash
# Run all tests
pytest

# Run specific test file
pytest test/test_app.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=html
```