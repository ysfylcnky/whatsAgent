import sqlite3
from datetime import datetime
DB_NAME = "usage_logs.db"

def initialize_database():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            timestamp TEXT,

            sender TEXT,

            model TEXT,

            prompt_tokens INTEGER,

            completion_tokens INTEGER,

            total_tokens INTEGER,

            cost REAL,

            response_time REAL

        )
    """)

    conn.commit()
    conn.close()

def log_usage(
    sender,
    model,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    cost,
    response_time
):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO usage_logs (
            timestamp,
            sender,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost,
            response_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            sender,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost,
            response_time
        )
    )

    conn.commit()
    conn.close()

def get_total_requests():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM usage_logs"
    )

    total = cursor.fetchone()[0]

    conn.close()

    return total

def get_total_tokens():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT SUM(total_tokens) FROM usage_logs"
    )

    total = cursor.fetchone()[0]

    conn.close()

    return total or 0

def get_total_cost():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT SUM(cost) FROM usage_logs"
    )

    total = cursor.fetchone()[0]

    conn.close()

    return round(total or 0, 6)

def get_average_response_time():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT AVG(response_time) FROM usage_logs"
    )

    average = cursor.fetchone()[0]

    conn.close()

    return round(average or 0, 3)

def get_usage_summary():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*),
            SUM(total_tokens),
            SUM(cost),
            AVG(response_time)
        FROM usage_logs
    """)

    result = cursor.fetchone()

    conn.close()

    return {

        "total_requests": result[0] or 0,

        "total_tokens": result[1] or 0,

        "total_cost": round(result[2] or 0, 6),

        "average_response_time": round(result[3] or 0, 3)

    }