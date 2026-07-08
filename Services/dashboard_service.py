from datetime import datetime, timedelta
import config
from Services.currency_service import get_usd_try_rate
from Services.usage_logger import get_connection

def get_business_summary(result, usd_try):

    unique_customers = result[1] or 0

    saved_hours = round(
        unique_customers * config.average_chat_time_minutes() / 60,
        2
    )

    employee_cost = round(
        saved_hours * config.employee_hourly_cost(),
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


# ============ Panel sayfaları: sayfalı liste sorguları ============

def _paginate(page, page_size):
    """1-tabanlı sayfa ve boyuttan güvenli (limit, offset) üretir."""
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1

    if page < 1:
        page = 1

    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 50

    page_size = max(1, min(page_size, 200))

    return page, page_size, (page - 1) * page_size


def _total_pages(total, page_size):
    if page_size <= 0:
        return 0
    return (total + page_size - 1) // page_size


def get_conversations_list(page=1, page_size=50):
    """Müşteri (sender) bazlı konuşma listesi; en son mesajı olan en üstte.

    Her satır: sender, ad_soyad (varsa), mesaj sayısı, son mesaj zamanı/özeti.
    Hata durumunda frontend'in patlamayacağı boş sayfalı yapı döner.
    """
    page, page_size, offset = _paginate(page, page_size)

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(DISTINCT sender) FROM conversations"
        )

        total = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT
                c.sender,
                MAX(cu.ad_soyad) AS ad_soyad,
                COUNT(*) AS msg_count,
                MAX(c.timestamp) AS last_time,
                SUBSTRING(
                    (SELECT c2.content FROM conversations c2
                     WHERE c2.sender = c.sender
                     ORDER BY c2.timestamp DESC, c2.id DESC
                     LIMIT 1),
                    1, 80
                ) AS last_content
            FROM conversations c
            LEFT JOIN customers cu ON cu.phone = c.sender
            GROUP BY c.sender
            ORDER BY last_time DESC
            LIMIT %s OFFSET %s
            """,
            (page_size, offset)
        )

        rows = cursor.fetchall()

        cursor.close()

        items = [
            {
                "sender": sender,
                "ad_soyad": ad_soyad,
                "msg_count": msg_count or 0,
                "last_time": last_time.strftime("%Y-%m-%d %H:%M") if last_time else None,
                "last_content": last_content or ""
            }
            for sender, ad_soyad, msg_count, last_time, last_content in rows
        ]

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": _total_pages(total, page_size)
        }

    except Exception as e:

        print("🔴 get_conversations_list hatası:", e)

        return {
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0
        }

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_conversation_detail(sender, page=1, page_size=50):
    """Tek bir müşterinin mesaj geçmişi (sayfalı).

    Sayfa 1 en YENİ mesajları içerir; sayfa içinde kronolojik (eski->yeni)
    sıralanır. 'Daha eski' için sonraki sayfalara gidilir.
    """
    page, page_size, offset = _paginate(page, page_size)

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT ad_soyad FROM customers WHERE phone = %s",
            (sender,)
        )

        row = cursor.fetchone()
        ad_soyad = row[0] if row else None

        cursor.execute(
            "SELECT COUNT(*) FROM conversations WHERE sender = %s",
            (sender,)
        )

        total = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT direction, content, timestamp
            FROM conversations
            WHERE sender = %s
            ORDER BY timestamp DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (sender, page_size, offset)
        )

        rows = cursor.fetchall()

        cursor.close()

        # Sorgu yeni->eski geldi; sayfa içinde kronolojik göstermek için ters çevir
        messages = [
            {
                "direction": direction,
                "content": content or "",
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S") if ts else None
            }
            for direction, content, ts in reversed(rows)
        ]

        return {
            "sender": sender,
            "ad_soyad": ad_soyad,
            "messages": messages,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": _total_pages(total, page_size)
        }

    except Exception as e:

        print("🔴 get_conversation_detail hatası:", e)

        return {
            "sender": sender,
            "ad_soyad": None,
            "messages": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0
        }

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_customers_list(page=1, page_size=50):
    """Sipariş vermiş müşteri listesi + sipariş özeti (sayfalı).

    Her satır: telefon, ad_soyad, ilk/son görülme, sipariş sayısı (is_update=0
    gerçek siparişler), son sipariş zamanı. En son aktif müşteri en üstte.
    """
    page, page_size, offset = _paginate(page, page_size)

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM customers")

        total = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT
                cu.phone,
                cu.ad_soyad,
                cu.first_seen,
                cu.last_seen,
                COUNT(CASE WHEN o.is_update = 0 THEN 1 END) AS order_count,
                MAX(o.timestamp) AS last_order_time
            FROM customers cu
            LEFT JOIN orders o ON o.customer_phone = cu.phone
            GROUP BY cu.phone, cu.ad_soyad, cu.first_seen, cu.last_seen
            ORDER BY cu.last_seen DESC
            LIMIT %s OFFSET %s
            """,
            (page_size, offset)
        )

        rows = cursor.fetchall()

        cursor.close()

        items = [
            {
                "phone": phone,
                "ad_soyad": ad_soyad,
                "first_seen": first_seen.strftime("%Y-%m-%d %H:%M") if first_seen else None,
                "last_seen": last_seen.strftime("%Y-%m-%d %H:%M") if last_seen else None,
                "order_count": order_count or 0,
                "last_order_time": last_order_time.strftime("%Y-%m-%d %H:%M") if last_order_time else None
            }
            for phone, ad_soyad, first_seen, last_seen, order_count, last_order_time in rows
        ]

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": _total_pages(total, page_size)
        }

    except Exception as e:

        print("🔴 get_customers_list hatası:", e)

        return {
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0
        }

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_customer_detail(phone, page=1, page_size=50):
    """Tek bir müşterinin sipariş geçmişi (sayfalı, yeni->eski).

    Her satır bir sipariş ya da güncellemedir (is_update ile işaretli).
    """
    page, page_size, offset = _paginate(page, page_size)

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT ad_soyad, first_seen, last_seen FROM customers WHERE phone = %s",
            (phone,)
        )

        row = cursor.fetchone()

        ad_soyad = row[0] if row else None
        first_seen = row[1].strftime("%Y-%m-%d %H:%M") if (row and row[1]) else None
        last_seen = row[2].strftime("%Y-%m-%d %H:%M") if (row and row[2]) else None

        cursor.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_phone = %s",
            (phone,)
        )

        total = cursor.fetchone()[0] or 0

        cursor.execute(
            """
            SELECT timestamp, urun, renk, beden, adet, odeme_sekli,
                   teslimat_adresi, is_update
            FROM orders
            WHERE customer_phone = %s
            ORDER BY timestamp DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (phone, page_size, offset)
        )

        rows = cursor.fetchall()

        cursor.close()

        orders = [
            {
                "timestamp": ts.strftime("%Y-%m-%d %H:%M") if ts else None,
                "urun": urun or "",
                "renk": renk or "",
                "beden": beden or "",
                "adet": adet if adet is not None else "",
                "odeme_sekli": odeme_sekli or "",
                "teslimat_adresi": teslimat_adresi or "",
                "is_update": bool(is_update)
            }
            for ts, urun, renk, beden, adet, odeme_sekli, teslimat_adresi, is_update in rows
        ]

        return {
            "phone": phone,
            "ad_soyad": ad_soyad,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "orders": orders,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": _total_pages(total, page_size)
        }

    except Exception as e:

        print("🔴 get_customer_detail hatası:", e)

        return {
            "phone": phone,
            "ad_soyad": None,
            "first_seen": None,
            "last_seen": None,
            "orders": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0
        }

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ============ AI Usage sayfası: detaylı kullanım analizi ============

# AI Usage trend penceresi (gün). Dashboard 14 gün gösterir; burada daha geniş.
AI_USAGE_TREND_DAYS = 30


def _ai_usage_empty(usd_try):
    """DB erişilemezse frontend'in patlamayacağı boş yapı."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    labels = [
        (today - timedelta(days=AI_USAGE_TREND_DAYS - 1 - i)).strftime("%Y-%m-%d")
        for i in range(AI_USAGE_TREND_DAYS)
    ]
    return {
        "summary": {
            "total_requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "total_cost_usd": 0, "total_cost_try": None,
            "avg_response_time": 0, "avg_cost_per_request": 0,
            "usd_try_rate": usd_try
        },
        "by_model": [],
        "daily": {
            "labels": labels,
            "cost": [0] * AI_USAGE_TREND_DAYS,
            "avg_response_time": [0] * AI_USAGE_TREND_DAYS,
            "requests": [0] * AI_USAGE_TREND_DAYS
        },
        "top_customers_by_cost": []
    }


def get_ai_usage_detail():
    """usage_logs üzerinden model bazlı maliyet, ortalama yanıt süresi trendi ve
    maliyete göre en yoğun müşterileri döndürür (Dashboard'dan daha detaylı).
    """
    usd_try = get_usd_try_rate()

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        # Genel özet
        cursor.execute("""
            SELECT COUNT(*), SUM(prompt_tokens), SUM(completion_tokens),
                   SUM(total_tokens), SUM(cost), AVG(response_time)
            FROM usage_logs
        """)
        r = cursor.fetchone()

        total_requests = r[0] or 0
        total_cost_usd = round(r[4] or 0, 6)
        avg_cost = round(total_cost_usd / total_requests, 6) if total_requests else 0

        summary = {
            "total_requests": total_requests,
            "prompt_tokens": int(r[1] or 0),
            "completion_tokens": int(r[2] or 0),
            "total_tokens": int(r[3] or 0),
            "total_cost_usd": total_cost_usd,
            "total_cost_try": round(total_cost_usd * usd_try, 2) if usd_try else None,
            "avg_response_time": round(r[5] or 0, 3),
            "avg_cost_per_request": avg_cost,
            "usd_try_rate": usd_try
        }

        # Model bazlı kırılım (maliyete göre azalan)
        cursor.execute("""
            SELECT model, COUNT(*), SUM(prompt_tokens), SUM(completion_tokens),
                   SUM(total_tokens), SUM(cost), AVG(response_time)
            FROM usage_logs
            GROUP BY model
            ORDER BY SUM(cost) DESC
        """)

        by_model = []
        for model, req, pt, ct, tt, cost, art in cursor.fetchall():
            req = req or 0
            cost = round(cost or 0, 6)
            by_model.append({
                "model": model,
                "requests": req,
                "prompt_tokens": int(pt or 0),
                "completion_tokens": int(ct or 0),
                "total_tokens": int(tt or 0),
                "cost_usd": cost,
                "avg_response_time": round(art or 0, 3),
                "avg_cost": round(cost / req, 6) if req else 0
            })

        # Günlük trend (son AI_USAGE_TREND_DAYS gün): maliyet + ort. yanıt süresi + istek
        start = (
            datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=AI_USAGE_TREND_DAYS - 1)
        )

        cursor.execute(
            """
            SELECT DATE(timestamp), COUNT(*), SUM(cost), AVG(response_time)
            FROM usage_logs
            WHERE timestamp >= %s
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp)
            """,
            (start,)
        )

        by_day = {
            str(d): (req or 0, round(cost or 0, 6), round(art or 0, 3))
            for d, req, cost, art in cursor.fetchall()
        }

        labels, d_cost, d_art, d_req = [], [], [], []
        for i in range(AI_USAGE_TREND_DAYS):
            key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            req, cost, art = by_day.get(key, (0, 0, 0))
            labels.append(key)
            d_req.append(req)
            d_cost.append(cost)
            d_art.append(art)

        # Maliyete göre en yoğun 10 müşteri
        cursor.execute("""
            SELECT sender, COUNT(*), SUM(cost)
            FROM usage_logs
            GROUP BY sender
            ORDER BY SUM(cost) DESC
            LIMIT 10
        """)

        top_customers = [
            {"sender": s, "requests": req or 0, "cost_usd": round(cost or 0, 6)}
            for s, req, cost in cursor.fetchall()
        ]

        cursor.close()

        return {
            "summary": summary,
            "by_model": by_model,
            "daily": {
                "labels": labels,
                "cost": d_cost,
                "avg_response_time": d_art,
                "requests": d_req
            },
            "top_customers_by_cost": top_customers
        }

    except Exception as e:

        print("🔴 get_ai_usage_detail hatası:", e)

        return _ai_usage_empty(usd_try)

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ======================================================================
# Reports (Raporlar) — tarih aralıklı kapsamlı özet + CSV export verileri
# ======================================================================

REPORT_DEFAULT_DAYS = 30


def _parse_date_range(start, end):
    """'YYYY-MM-DD' string'lerinden (start_dt, end_exclusive_dt, start_str, end_str) üretir.

    Aralık her iki uçta dahildir; üst sınır (end + 1 gün) hariç tutulur ki bitiş
    günü de kapsansın. Varsayılan son REPORT_DEFAULT_DAYS gün (bugün dahil).
    start > end ise takas edilir; geçersiz değerlerde varsayılana düşülür.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def _parse(v):
        try:
            return datetime.strptime(str(v)[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            return None

    end_dt = _parse(end) or today
    start_dt = _parse(start) or (end_dt - timedelta(days=REPORT_DEFAULT_DAYS - 1))

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    end_exclusive = end_dt + timedelta(days=1)

    return start_dt, end_exclusive, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def _report_summary_empty(start_str, end_str, usd_try):
    """DB erişilemezse frontend'in patlamayacağı boş rapor yapısı."""
    return {
        "start": start_str,
        "end": end_str,
        "usd_try_rate": usd_try,
        "ai": {
            "requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "cost_usd": 0, "cost_try": None,
            "avg_response_time": 0
        },
        "orders": {"count": 0, "update_count": 0, "total_quantity": 0, "by_payment": []},
        "messages": {"incoming": 0, "outgoing": 0, "unique_customers": 0}
    }


def get_report_summary(start=None, end=None):
    """Tarih aralığı için kapsamlı özet: AI kullanımı + sipariş + mesaj.

    Aralık dahil (start ve end günleri). Veri yoksa/DB düşse bile boş yapı döner.
    """
    start_dt, end_ex, start_str, end_str = _parse_date_range(start, end)

    usd_try = get_usd_try_rate()

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        # --- AI kullanımı ---
        cursor.execute(
            """
            SELECT COUNT(*), SUM(prompt_tokens), SUM(completion_tokens),
                   SUM(total_tokens), SUM(cost), AVG(response_time)
            FROM usage_logs
            WHERE timestamp >= %s AND timestamp < %s
            """,
            (start_dt, end_ex)
        )
        a = cursor.fetchone()
        ai_cost_usd = round(a[4] or 0, 6)
        ai = {
            "requests": a[0] or 0,
            "prompt_tokens": int(a[1] or 0),
            "completion_tokens": int(a[2] or 0),
            "total_tokens": int(a[3] or 0),
            "cost_usd": ai_cost_usd,
            "cost_try": round(ai_cost_usd * usd_try, 2) if usd_try else None,
            "avg_response_time": round(a[5] or 0, 3)
        }

        # --- Siparişler (gerçek sipariş vs güncelleme ayrımı) ---
        cursor.execute(
            """
            SELECT
                COUNT(CASE WHEN is_update = 0 THEN 1 END),
                COUNT(CASE WHEN is_update = 1 THEN 1 END),
                SUM(CASE WHEN is_update = 0 THEN adet END)
            FROM orders
            WHERE timestamp >= %s AND timestamp < %s
            """,
            (start_dt, end_ex)
        )
        o = cursor.fetchone()
        orders = {
            "count": o[0] or 0,
            "update_count": o[1] or 0,
            "total_quantity": int(o[2] or 0)
        }

        # Ödeme şekli dağılımı (yalnız gerçek siparişler)
        cursor.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(odeme_sekli), ''), 'Belirtilmemiş'), COUNT(*)
            FROM orders
            WHERE is_update = 0 AND timestamp >= %s AND timestamp < %s
            GROUP BY 1
            ORDER BY COUNT(*) DESC
            """,
            (start_dt, end_ex)
        )
        orders["by_payment"] = [
            {"odeme_sekli": p, "count": c or 0}
            for p, c in cursor.fetchall()
        ]

        # --- Mesajlar ---
        cursor.execute(
            """
            SELECT
                COUNT(CASE WHEN direction = 'gelen' THEN 1 END),
                COUNT(CASE WHEN direction = 'giden' THEN 1 END),
                COUNT(DISTINCT sender)
            FROM conversations
            WHERE timestamp >= %s AND timestamp < %s
            """,
            (start_dt, end_ex)
        )
        m = cursor.fetchone()
        messages = {
            "incoming": m[0] or 0,
            "outgoing": m[1] or 0,
            "unique_customers": m[2] or 0
        }

        cursor.close()

        return {
            "start": start_str,
            "end": end_str,
            "usd_try_rate": usd_try,
            "ai": ai,
            "orders": orders,
            "messages": messages
        }

    except Exception as e:

        print("🔴 get_report_summary hatası:", e)

        return _report_summary_empty(start_str, end_str, usd_try)

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_orders_export_rows(start=None, end=None):
    """CSV export için aralıktaki ham sipariş satırları (list[list])."""
    start_dt, end_ex, _, _ = _parse_date_range(start, end)

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT timestamp, customer_phone, ad_soyad, telefon, urun, renk,
                   beden, adet, odeme_sekli, teslimat_adresi, is_update
            FROM orders
            WHERE timestamp >= %s AND timestamp < %s
            ORDER BY timestamp
            """,
            (start_dt, end_ex)
        )

        rows = cursor.fetchall()

        cursor.close()

        out = []
        for (ts, phone, ad, tel, urun, renk, beden, adet, odeme, adres, isu) in rows:
            out.append([
                ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "",
                phone or "",
                ad or "",
                tel or "",
                urun or "",
                renk or "",
                beden or "",
                adet if adet is not None else "",
                odeme or "",
                adres or "",
                "guncelleme" if isu else "siparis"
            ])
        return out

    except Exception as e:

        print("🔴 get_orders_export_rows hatası:", e)

        return []

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_daily_usage_export_rows(start=None, end=None):
    """CSV export için günlük AI kullanım özeti satırları (list[list])."""
    start_dt, end_ex, _, _ = _parse_date_range(start, end)

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DATE(timestamp), COUNT(*), SUM(prompt_tokens),
                   SUM(completion_tokens), SUM(total_tokens), SUM(cost)
            FROM usage_logs
            WHERE timestamp >= %s AND timestamp < %s
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp)
            """,
            (start_dt, end_ex)
        )

        rows = cursor.fetchall()

        cursor.close()

        out = []
        for (d, req, pt, ct, tt, cost) in rows:
            out.append([
                str(d),
                req or 0,
                int(pt or 0),
                int(ct or 0),
                int(tt or 0),
                round(cost or 0, 6)
            ])
        return out

    except Exception as e:

        print("🔴 get_daily_usage_export_rows hatası:", e)

        return []

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
