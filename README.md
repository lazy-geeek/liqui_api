# Liqui API

A high-performance REST API for querying cryptocurrency liquidation data, built with FastAPI and MySQL.

## Overview

Liqui API provides real-time access to cryptocurrency liquidation data with powerful aggregation and filtering capabilities. It's designed for traders, analysts, and developers who need reliable access to liquidation information across various trading pairs.

## Features

- **Real-time liquidation data** - Query individual liquidation orders or aggregated data
- **Time-based aggregation** - Aggregate liquidations by customizable timeframes (5m, 1h, 1d, etc.)
- **Flexible timestamp formats** - Supports both Unix timestamps and ISO 8601 date strings
- **Symbol filtering** - Query specific trading pairs or retrieve all available symbols
- **High performance** - Built with FastAPI and optimized SQL queries
- **Production-ready** - Includes comprehensive error handling and logging

## Technology Stack

- **Framework**: FastAPI (v0.115.0)
- **Server**: Uvicorn with Gunicorn workers
- **Database**: MySQL
- **Python**: 3.12+
- **Package Management**: Poetry
- **Deployment**: Heroku/Dokku ready

## Prerequisites

- Python 3.12 or higher
- MySQL database with liquidation data
- Poetry (for dependency management)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/liqui_api.git
cd liqui_api
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Set up environment variables:
```bash
export DB_HOST=your-mysql-host
export DB_USER=your-mysql-user
export DB_PASSWORD=your-mysql-password
export DB_DATABASE=your-database-name
export DB_LIQ_TABLENAME=your-table-name  # Optional, defaults to "binance_liqs"
```

## Running the Application

### Development Mode

```bash
# Run with auto-reload
uvicorn app:app --reload

# Or use nohup to avoid startup delays
nohup uvicorn app:app --reload &
```

### Production Mode

```bash
# Run with Gunicorn (4 workers)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
```

## API Endpoints

### 1. Get Aggregated Liquidations

Retrieve liquidation data aggregated by timeframe and side.

**Endpoint**: `GET /api/liquidations`

**Parameters**:
- `symbol` (required): Trading symbol (e.g., "BTCUSDT")
- `timeframe` (optional): Aggregation period (e.g., "5m", "1h", "1d")
- `start_timestamp` (optional): Start time (Unix ms or ISO format)
- `end_timestamp` (optional): End time (Unix ms or ISO format)

**Example Request**:
```bash
curl "http://localhost:8000/api/liquidations?symbol=BTCUSDT&timeframe=1h&start_timestamp=2021-01-01T00:00:00Z&end_timestamp=2021-01-02T00:00:00Z"
```

**Example Response**:
```json
[
  {
    "time_bucket": 1609459200000,
    "side": "buy",
    "total_usd_size": 1234567.89,
    "count": 42
  },
  {
    "time_bucket": 1609459200000,
    "side": "sell",
    "total_usd_size": 987654.32,
    "count": 35
  }
]
```

### 2. Get Available Symbols

Retrieve all trading symbols available in the database.

**Endpoint**: `GET /api/symbols`

**Example Request**:
```bash
curl "http://localhost:8000/api/symbols"
```

**Example Response**:
```json
[
  "BTCUSDT",
  "ETHUSDT",
  "BNBUSDT",
  "ADAUSDT"
]
```

### 3. Get Individual Liquidation Orders

Retrieve detailed liquidation orders for a specific symbol.

**Endpoint**: `GET /api/liquidation-orders`

**Parameters** (Two modes available):

**Mode 1 - Time Range**:
- `symbol` (required): Trading symbol
- `start_timestamp`: Start time (Unix ms or ISO format)
- `end_timestamp`: End time (Unix ms or ISO format)

**Mode 2 - Latest Orders**:
- `symbol` (required): Trading symbol
- `limit`: Number of recent orders (1-1000)

**Example Request (Time Range)**:
```bash
curl "http://localhost:8000/api/liquidation-orders?symbol=BTCUSDT&start_timestamp=2021-01-01T00:00:00Z&end_timestamp=2021-01-01T01:00:00Z"
```

**Example Request (Latest Orders)**:
```bash
curl "http://localhost:8000/api/liquidation-orders?symbol=BTCUSDT&limit=100"
```

**Example Response**:
```json
[
  {
    "symbol": "BTCUSDT",
    "side": "sell",
    "order_type": "LIMIT",
    "time_in_force": "GTC",
    "original_quantity": "0.5",
    "price": "45000.00",
    "average_price": "45000.00",
    "order_status": "FILLED",
    "order_last_filled_quantity": "0.5",
    "order_filled_accumulated_quantity": "0.5",
    "order_trade_time": 1609459200000
  }
]
```

## Timestamp Formats

The API accepts timestamps in two formats:

1. **Unix timestamp in milliseconds**: `1609459200000`
2. **ISO 8601 format**: `2021-01-01T00:00:00Z`

## Timeframe Options

For aggregated data, you can use the following timeframe suffixes:
- Minutes: `1m`, `5m`, `15m`, `30m`
- Hours: `1h`, `4h`, `12h`
- Days: `1d`, `3d`, `7d`

## Database Schema

The API expects a MySQL table with the following columns:

- `symbol`: Trading pair symbol (VARCHAR)
- `order_trade_time`: Timestamp in milliseconds (BIGINT)
- `side`: Trade side - buy/sell (VARCHAR)
- `usd_size`: Liquidation size in USD (DECIMAL)
- `order_type`: Order type (VARCHAR)
- `time_in_force`: Time in force (VARCHAR)
- `original_quantity`: Original order quantity (DECIMAL)
- `price`: Order price (DECIMAL, nullable)
- `average_price`: Average execution price (DECIMAL)
- `order_status`: Order status (VARCHAR)
- `order_last_filled_quantity`: Last filled quantity (DECIMAL)
- `order_filled_accumulated_quantity`: Total filled quantity (DECIMAL)

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test file
pytest test/test_app.py -v
```

## Deployment

The application includes a `Procfile` for easy deployment to Heroku or Dokku:

```bash
web: gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app
```

### Deploy to Heroku

1. Create a new Heroku app
2. Add MySQL addon or configure external database
3. Set environment variables
4. Push to Heroku

### Deploy to Dokku

1. Create a new Dokku app
2. Link MySQL database
3. Set environment variables
4. Push to Dokku git remote

## Error Handling

The API returns appropriate HTTP status codes:

- `200 OK`: Successful request
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Database connection error

## Performance Considerations

- Uses SQL aggregation for efficient time-based grouping
- Database indexes recommended on `symbol`, `order_trade_time`, and `side` columns
- Connection pooling handled automatically by the database utilities
- Supports multiple worker processes for high concurrency

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or contributions, please open an issue on GitHub.