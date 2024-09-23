from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel
from datetime import datetime, timedelta
import mysql.connector
import os

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
    start_timestamp: str
    end_timestamp: str


@app.post("/api/liquidations")
async def post_liquidations(liquidation_request: LiquidationRequest = Body(...)):
    table_name = os.getenv("DB_LIQ_TABLENAME", "binance_liqs")
    try:
        start_datetime = datetime.strptime(
            liquidation_request.start_timestamp, "%Y-%m-%d %H:%M"
        )
        end_datetime = datetime.strptime(
            liquidation_request.end_timestamp, "%Y-%m-%d %H:%M"
        )
        start_timestamp = int(start_datetime.timestamp())
        end_timestamp = int(end_datetime.timestamp())
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="start_timestamp and end_timestamp must be valid datetime strings in the format 'YYYY-MM-DD HH:MM'",
        )

    timeframe_seconds = convert_timeframe_to_seconds(liquidation_request.timeframe)
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
        SELECT symbol, {timeframe_seconds} AS timeframe, {int(current_start.timestamp() * 1000)} AS start_timestamp, {int(current_end.timestamp() * 1000)} AS end_timestamp, SUM(usd_size) AS cumulated_usd_size
        FROM {table_name}
        WHERE LOWER(symbol) = %s AND order_trade_time >= %s AND order_trade_time < %s
        GROUP BY symbol, timeframe, start_timestamp, end_timestamp
        """

        cursor.execute(
            query,
            (
                liquidation_request.symbol.lower(),
                int(current_start.timestamp() * 1000),
                int(current_end.timestamp() * 1000),
            ),
        )
        result = cursor.fetchone()
        if result:
            results.append(
                {
                    "symbol": result[0],
                    "timeframe": liquidation_request.timeframe,
                    "start_timestamp": datetime.fromtimestamp(
                        result[2] / 1000
                    ).isoformat(),
                    "end_timestamp": datetime.fromtimestamp(
                        result[3] / 1000
                    ).isoformat(),
                    "cumulated_usd_size": float(result[4]),
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