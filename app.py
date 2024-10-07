from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel
from datetime import datetime, timedelta
import mysql.connector
import os
import re

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


def convert_timeframe_to_seconds(timeframe: str) -> int:
    timeframe = timeframe.lower()
    if timeframe.endswith("m"):
        return int(timeframe[:-1]) * 60
    elif timeframe.endswith("h"):
        return int(timeframe[:-1]) * 3600
    elif timeframe.endswith("d"):
        return int(timeframe[:-1]) * 86400
    else:
        raise ValueError("Invalid timeframe format")


class LiquidationRequest(BaseModel):
    symbol: str
    timeframe: str
    start_timestamp_iso: str
    end_timestamp_iso: str


@app.get("/api/liquidations")
async def get_liquidations(symbol: str = Query(..., description="Symbol to filter by"), timeframe: str = Query(..., description="Timeframe for aggregation"), start_timestamp_iso: str = Query(..., description="Start timestamp in ISO format"), end_timestamp_iso: str = Query(..., description="End timestamp in ISO format")):
    table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
    try:
        start_datetime = datetime.fromisoformat(start_timestamp_iso)
        end_datetime = datetime.fromisoformat(end_timestamp_iso)
        start_timestamp = int(start_datetime.timestamp())
        end_timestamp = int(end_datetime.timestamp())
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="start_timestamp and end_timestamp must be valid datetime strings in the format 'YYYY-MM-DD HH:MM'",
        )

    timeframe_seconds = convert_timeframe_to_seconds(timeframe)
    if start_timestamp < 0 or end_timestamp < 0:
        raise HTTPException(
            status_code=400,
            detail="start_timestamp and end_timestamp must be non-negative integers",
        )

    if start_datetime > end_datetime:
        raise HTTPException(
            status_code=400, detail="start_timestamp must be before end_timestamp"
        )

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    results = []
    current_start = start_datetime
    while current_start < end_datetime:
        current_end = current_start + timedelta(seconds=timeframe_seconds)
        query = f"""
        SELECT symbol, {timeframe_seconds} AS timeframe, {int(current_start.timestamp() * 1000)} AS start_timestamp, {int(current_end.timestamp() * 1000)} AS end_timestamp, side, SUM(usd_size) AS cumulated_usd_size
        FROM {table_name}
        WHERE LOWER(symbol) = %s AND order_trade_time >= %s AND order_trade_time < %s
        GROUP BY symbol, timeframe, start_timestamp, end_timestamp, side
        """

        cursor.execute(
            query,
            (
                symbol.lower(),
                int(current_start.timestamp() * 1000),
                int(current_end.timestamp() * 1000),
            ),
        )
        results_for_timeframe = cursor.fetchall()
        for result in results_for_timeframe:
            results.append(
                {
                    "symbol": result[0],
                    "timeframe": timeframe,
                    "start_timestamp": result[2],
                    "end_timestamp": result[3],
                    "start_timestamp_iso": datetime.fromtimestamp(
                        result[2] / 1000
                    ).isoformat(),
                    "end_timestamp_iso": datetime.fromtimestamp(
                        result[3] / 1000
                    ).isoformat(),
                    "side": result[4],
                    "cumulated_usd_size": float(result[5]),
                }
            )
        current_start = current_end

    if not results:
        raise HTTPException(
            status_code=404, detail="No data found for the given parameters"
        )

    cursor.close()
    conn.close()

    return results


@app.get("/api/symbols")
async def get_symbols():
    conn = mysql.connector.connect(**db_config)
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
    conn.close()

    return symbols
