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
- **Database**: MySQL (via mysql-connector-python v9.0.0)
- **Package Management**: Poetry
- **Deployment**: Configured for Heroku/Dokku (Procfile present)

## Project Structure

```
liqui_api/
├── app.py              # Main FastAPI application file
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

### Key Features

1. **Time-based Aggregation**: Converts timeframes (m/h/d) to milliseconds for SQL grouping
2. **Flexible Timestamp Input**: Accepts both Unix timestamps (ms) and ISO format strings via `parse_timestamp()` utility
3. **Error Handling**: Comprehensive error handling with appropriate HTTP status codes
4. **Database Connection Management**: Proper connection lifecycle with cleanup
5. **Input Validation**: Uses Pydantic models and FastAPI validation
6. **Test Coverage**: Comprehensive unit and integration tests using pytest

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

```bash
DB_HOST=<mysql-host>
DB_USER=<mysql-user>
DB_PASSWORD=<mysql-password>
DB_DATABASE=<database-name>
DB_LIQ_TABLENAME=<table-name>  # Optional, defaults to "binance_liqs"
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

1. Ensure all environment variables are set in the deployment environment
2. The application uses 4 worker processes (see Procfile)
3. Database must be accessible from the deployment environment
4. Consider adding health check endpoint for monitoring

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