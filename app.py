from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import mysql.connector
import os
import re
from functools import lru_cache

app = FastAPI()


# Cache for database connections
def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"FATAL: Could not connect to database: {err}")
        raise HTTPException(status_code=503, detail="Database service unavailable")


# MySQL database configuration from environment variables
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_DATABASE"),
}

# Table name
table_name = os.getenv("DB_LIQ_TABLENAME")


def convert_timeframe_to_milliseconds(timeframe: str) -> int:
    timeframe = timeframe.lower()
    if timeframe.endswith("m"):
        return int(timeframe[:-1]) * 60 * 1000
    elif timeframe.endswith("h"):
        return int(timeframe[:-1]) * 3600 * 1000
    elif timeframe.endswith("d"):
        return int(timeframe[:-1]) * 86400 * 1000
    else:
        raise ValueError("Invalid timeframe format")


class LiquidationRequest(BaseModel):
    symbol: str
    timeframe: str
    start_timestamp_iso: str
    end_timestamp_iso: str


@app.get("/api/liquidations")
async def get_liquidations(
    symbol: str = Query(..., description="Symbol to filter by"),
    timeframe: str = Query(..., description="Timeframe for aggregation"),
    start_timestamp: str = Query(
        ..., description="Start timestamp in ISO or Unix format"
    ),
    end_timestamp: str = Query(..., description="End timestamp in ISO or Unix format"),
):
    table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
    try:
        if start_timestamp.isdigit():
            start_timestamp = int(start_timestamp)
        else:
            start_timestamp = int(
                datetime.fromisoformat(start_timestamp).timestamp() * 1000
            )

        if end_timestamp.isdigit():
            end_timestamp = int(end_timestamp)
        else:
            end_timestamp = int(
                datetime.fromisoformat(end_timestamp).timestamp() * 1000
            )
    except (TypeError, ValueError):
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

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

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

        cursor.execute(
            query,
            (
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
            ),
        )
        results = [
            {
                "timestamp": result[1],
                "timestamp_iso": datetime.fromtimestamp(
                    int(result[1]) / 1000, tz=timezone.utc
                ).isoformat(),
                "side": result[3],
                "cumulated_usd_size": float(result[4]),
            }
            for result in cursor.fetchall()
        ]

        if not results:
            raise HTTPException(
                status_code=404, detail="No data found for the given parameters"
            )

        cursor.close()
        return results

    except mysql.connector.Error as err:
        print(f"ERROR: Database error in /api/liquidations: {err}")
        raise HTTPException(status_code=500, detail="Internal database error")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"ERROR: Unexpected error in /api/liquidations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn and conn.is_connected():
            conn.close()


@app.get("/api/symbols")
async def get_symbols():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT DISTINCT symbol
        FROM {}
        WHERE symbol NOT REGEXP '[0-9]+$'
        ORDER BY symbol
        """.format(
            table_name
        )

        cursor.execute(query)
        results = cursor.fetchall()

        symbols = [result[0] for result in results]

        cursor.close()
        return symbols

    except mysql.connector.Error as err:
        print(f"ERROR: Database error in /api/symbols: {err}")
        raise HTTPException(status_code=500, detail="Internal database error")
    except Exception as e:
        print(f"ERROR: Unexpected error in /api/symbols: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if conn and conn.is_connected():
            conn.close()
