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
├── pyproject.toml      # Poetry configuration
├── poetry.lock         # Poetry lock file
├── requirements.txt    # Auto-generated from Poetry
├── Procfile           # Deployment configuration
├── app.log            # Application log file
├── to_dos.md          # TODO file (mentions Dokku deployment)
└── .gitignore         # Git ignore configuration
```

## Key Commands

### Development
```bash
# Install dependencies using Poetry
poetry install

# Run development server
uvicorn app:app --reload

# Alternative: Run with gunicorn (production-like)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
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
   - Parameters:
     - `symbol`: Trading symbol to filter by (required)
     - `timeframe`: Aggregation timeframe (e.g., "5m", "1h", "1d")
     - `start_timestamp`: Start time (Unix ms or ISO format)
     - `end_timestamp`: End time (Unix ms or ISO format)
   - Returns aggregated liquidation data grouped by timeframe and side

2. **GET /api/symbols**
   - Get list of all available trading symbols
   - Filters out symbols ending with numbers
   - Returns sorted list of symbols

### Key Features

1. **Time-based Aggregation**: Converts timeframes (m/h/d) to milliseconds for SQL grouping
2. **Flexible Timestamp Input**: Accepts both Unix timestamps (ms) and ISO format strings
3. **Error Handling**: Comprehensive error handling with appropriate HTTP status codes
4. **Database Connection Management**: Proper connection lifecycle with cleanup
5. **Input Validation**: Uses Pydantic models and FastAPI validation

## Database Schema

The application expects a MySQL table with at least these columns:
- `symbol`: Trading pair symbol (e.g., "BTCUSDT")
- `order_trade_time`: Timestamp in milliseconds
- `side`: Trade side (buy/sell)
- `usd_size`: Size of the liquidation in USD

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
1. Add route handler in `app.py`
2. Define Pydantic models if needed for request/response validation
3. Follow existing pattern for database connection management
4. Add appropriate error handling

### Modifying Database Queries
1. All queries use parameterized statements for security
2. Table name is configurable via environment variable
3. Always close database connections in finally blocks

### Testing
No test files are currently present. Consider adding:
- Unit tests for utility functions (e.g., `convert_timeframe_to_milliseconds`)
- Integration tests for API endpoints
- Database connection tests