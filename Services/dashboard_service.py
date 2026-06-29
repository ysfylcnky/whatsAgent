import sqlite3
from config import (
    AVERAGE_CHAT_TIME_MINUTES,
    EMPLOYEE_HOURLY_COST
)
from Services.currency_service import get_usd_try_rate
from Services.usage_logger import DB_NAME

def get_business_summary(result, usd_try):

    unique_customers = result[1] or 0

    saved_hours = round(
        unique_customers * AVERAGE_CHAT_TIME_MINUTES / 60,
        2
    )

    employee_cost = round(
        saved_hours * EMPLOYEE_HOURLY_COST,
        2
    )

    total_cost_usd = result[5] or 0

    ai_cost_try = None

    estimated_savings = None

    if usd_try is not None:

        ai_cost_try = round(
            total_cost_usd * usd_try,
            2
        )

        estimated_savings = round(
            employee_cost - ai_cost_try,
            2
        )

    return {
        "unique_customers": unique_customers,

        "total_requests": result[0] or 0,

        "estimated_saved_hours": saved_hours,

        "estimated_employee_cost": employee_cost,

        "ai_cost_try": ai_cost_try,

        "estimated_savings": estimated_savings
    }
def get_usage_summary(result, usd_try):

    total_cost_usd = round(
        result[5] or 0,
        6
    )

    total_cost_try = None

    if usd_try is not None:

        total_cost_try = round(
            total_cost_usd * usd_try,
            2
        )

    return {
        "prompt_tokens": result[2] or 0,

        "completion_tokens": result[3] or 0,

        "total_tokens": result[4] or 0,

        "total_cost_usd": total_cost_usd,

        "total_cost_try": total_cost_try,

        "usd_try_rate": usd_try
    }
def get_performance_summary(result):

    return {

        "average_response_time": round(
            result[6] or 0,
            3
        )

    }
def get_dashboard_data():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""

        SELECT

            COUNT(*) as total_requests,

            COUNT(DISTINCT sender) as unique_customers,

            SUM(prompt_tokens),

            SUM(completion_tokens),

            SUM(total_tokens),

            SUM(cost),

            AVG(response_time)

        FROM usage_logs

    """)

    result = cursor.fetchone()

    conn.close()
    usd_try = get_usd_try_rate()

    return {

        "business": get_business_summary(
            result,
            usd_try
        ),

        "usage": get_usage_summary(
            result,
            usd_try
        ),

        "performance": get_performance_summary(
            result
        )

    }