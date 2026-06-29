from datetime import datetime, timedelta
from config import (
    AVERAGE_CHAT_TIME_MINUTES,
    EMPLOYEE_HOURLY_COST
)
from Services.currency_service import get_usd_try_rate
from Services.usage_logger import get_connection

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
        # MySQL SUM(INT) -> Decimal döner; orijinal int dönüş tipini koru
        "prompt_tokens": int(result[2] or 0),

        "completion_tokens": int(result[3] or 0),

        "total_tokens": int(result[4] or 0),

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


def _get_daily_trend(cursor):
    """Son 14 günün gün bazlı dağılımı.

    Veri olmayan günler 0 ile doldurulur; dizi her zaman 14 elemanlı ve
    tarih sırası kesintisizdir.
    """
    today = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    start = today - timedelta(days=13)

    cursor.execute(
        """
        SELECT
            DATE(timestamp) AS d,
            COUNT(*),
            SUM(total_tokens),
            SUM(cost),
            COUNT(DISTINCT sender)
        FROM usage_logs
        WHERE timestamp >= %s
        GROUP BY DATE(timestamp)
        ORDER BY d
        """,
        (start,)
    )

    rows = cursor.fetchall()

    # Sorgu sonucunu tarih -> değerler sözlüğüne çevir
    by_day = {}

    for d, req, tok, cost, cust in rows:
        by_day[str(d)] = (
            req or 0,
            int(tok or 0),
            round(cost or 0, 6),
            cust or 0
        )

    labels = []
    requests = []
    tokens = []
    cost_arr = []
    customers = []

    # Eksik günleri Python tarafında tamamla
    for i in range(14):

        day = start + timedelta(days=i)
        key = day.strftime("%Y-%m-%d")

        req, tok, cost, cust = by_day.get(key, (0, 0, 0, 0))

        labels.append(key)
        requests.append(req)
        tokens.append(tok)
        cost_arr.append(cost)
        customers.append(cust)

    return {
        "labels": labels,
        "requests": requests,
        "tokens": tokens,
        "cost": cost_arr,
        "customers": customers
    }


def _get_hourly_activity(cursor):
    """0-23 arası 24 saatin tamamı; tüm kayıtlar üzerinden saat dağılımı."""
    cursor.execute(
        """
        SELECT HOUR(timestamp), COUNT(*)
        FROM usage_logs
        GROUP BY HOUR(timestamp)
        """
    )

    rows = cursor.fetchall()

    by_hour = {int(h): (c or 0) for h, c in rows}

    labels = [f"{h:02d}:00" for h in range(24)]

    requests = [by_hour.get(h, 0) for h in range(24)]

    return {
        "labels": labels,
        "requests": requests
    }


def _get_model_distribution(cursor):
    """Model alanına göre istek sayısı (çok -> az)."""
    cursor.execute(
        """
        SELECT model, COUNT(*)
        FROM usage_logs
        GROUP BY model
        ORDER BY COUNT(*) DESC
        """
    )

    rows = cursor.fetchall()

    return {
        "labels": [r[0] for r in rows],
        "requests": [r[1] for r in rows]
    }


def _get_top_customers(cursor):
    """En çok istek atan ilk 8 müşteri."""
    cursor.execute(
        """
        SELECT sender, COUNT(*)
        FROM usage_logs
        GROUP BY sender
        ORDER BY COUNT(*) DESC
        LIMIT 8
        """
    )

    rows = cursor.fetchall()

    return {
        "labels": [r[0] for r in rows],
        "requests": [r[1] for r in rows]
    }


def _get_recent_activity(cursor):
    """Son 10 kayıt; timestamp 'YYYY-MM-DD HH:MM:SS' string olarak verilir."""
    cursor.execute(
        """
        SELECT sender, model, total_tokens, response_time, timestamp
        FROM usage_logs
        ORDER BY timestamp DESC
        LIMIT 10
        """
    )

    rows = cursor.fetchall()

    activity = []

    for sender, model, total_tokens, response_time, ts in rows:

        activity.append({
            "sender": sender,
            "model": model,
            "total_tokens": total_tokens or 0,
            "response_time": response_time or 0,
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if ts else None
        })

    return activity


def _empty_dashboard(usd_try):
    """Veritabanı erişilemezse frontend'in patlamayacağı anlamlı boş yapı."""
    zero = (0, 0, 0, 0, 0, 0, 0)

    return {

        "business": get_business_summary(zero, usd_try),

        "usage": get_usage_summary(zero, usd_try),

        "performance": get_performance_summary(zero),

        "charts": {

            "daily_trend": {
                "labels": [
                    (
                        datetime.now().replace(
                            hour=0, minute=0, second=0, microsecond=0
                        ) - timedelta(days=13 - i)
                    ).strftime("%Y-%m-%d")
                    for i in range(14)
                ],
                "requests": [0] * 14,
                "tokens": [0] * 14,
                "cost": [0] * 14,
                "customers": [0] * 14
            },

            "hourly_activity": {
                "labels": [f"{h:02d}:00" for h in range(24)],
                "requests": [0] * 24
            },

            "model_distribution": {
                "labels": [],
                "requests": []
            },

            "top_customers": {
                "labels": [],
                "requests": []
            }

        },

        "recent_activity": []

    }


def get_dashboard_data():

    usd_try = get_usd_try_rate()

    conn = None

    try:

        conn = get_connection()

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

        charts = {
            "daily_trend": _get_daily_trend(cursor),
            "hourly_activity": _get_hourly_activity(cursor),
            "model_distribution": _get_model_distribution(cursor),
            "top_customers": _get_top_customers(cursor)
        }

        recent_activity = _get_recent_activity(cursor)

        cursor.close()

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
            ),

            "charts": charts,

            "recent_activity": recent_activity

        }

    except Exception as e:

        print("🔴 get_dashboard_data hatası:", e)

        return _empty_dashboard(usd_try)

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
