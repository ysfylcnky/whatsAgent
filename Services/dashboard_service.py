from datetime import datetime, timedelta
import config
from Services.currency_service import get_usd_try_rate
from Services.usage_logger import get_connection
from sqlalchemy import func, distinct, select, extract, case
from Services.db import get_session
from Services.models import Conversation, Customer, UsageLog, Order

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


def _get_daily_trend():
    """Son 14 günün gün bazlı dağılımı. (Faz 0: ORM, kendi oturumunu açar.)

    Veri olmayan günler 0 ile doldurulur; dizi her zaman 14 elemanlı ve
    tarih sırası kesintisizdir. DATE(timestamp) yerine dialect-bağımsız
    func.date kullanılır (MySQL/SQLite'ta aynı sonuç).
    """
    today = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    start = today - timedelta(days=13)

    with get_session() as session:
        rows = (
            session.query(
                func.date(UsageLog.timestamp),
                func.count(),
                func.sum(UsageLog.total_tokens),
                func.sum(UsageLog.cost),
                func.count(distinct(UsageLog.sender)),
            )
            .filter(UsageLog.timestamp >= start)
            .group_by(func.date(UsageLog.timestamp))
            .order_by(func.date(UsageLog.timestamp))
            .all()
        )

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


def _get_hourly_activity():
    """0-23 arası 24 saatin tamamı; saat dağılımı. (Faz 0: ORM.)

    HOUR(timestamp) yerine dialect-bağımsız extract('hour', ...) kullanılır.
    """
    with get_session() as session:
        rows = (
            session.query(
                extract("hour", UsageLog.timestamp),
                func.count(),
            )
            .group_by(extract("hour", UsageLog.timestamp))
            .all()
        )

    by_hour = {int(h): (c or 0) for h, c in rows}

    labels = [f"{h:02d}:00" for h in range(24)]

    requests = [by_hour.get(h, 0) for h in range(24)]

    return {
        "labels": labels,
        "requests": requests
    }


def _get_model_distribution():
    """Model alanına göre istek sayısı (çok -> az). (Faz 0: ORM.)"""
    with get_session() as session:
        rows = (
            session.query(UsageLog.model, func.count())
            .group_by(UsageLog.model)
            .order_by(func.count().desc())
            .all()
        )

    return {
        "labels": [r[0] for r in rows],
        "requests": [r[1] for r in rows]
    }


def _get_top_customers():
    """En çok istek atan ilk 8 müşteri. (Faz 0: ORM, kendi oturumunu açar.)"""
    with get_session() as session:
        rows = (
            session.query(UsageLog.sender, func.count())
            .group_by(UsageLog.sender)
            .order_by(func.count().desc())
            .limit(8)
            .all()
        )

    return {
        "labels": [r[0] for r in rows],
        "requests": [r[1] for r in rows]
    }


def _get_recent_activity():
    """Son 10 kayıt; timestamp 'YYYY-MM-DD HH:MM:SS' string. (Faz 0: ORM.)"""
    with get_session() as session:
        rows = (
            session.query(
                UsageLog.sender,
                UsageLog.model,
                UsageLog.total_tokens,
                UsageLog.response_time,
                UsageLog.timestamp,
            )
            .order_by(UsageLog.timestamp.desc())
            .limit(10)
            .all()
        )

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

    try:

        # Faz 0: ana özet sorgusu da ORM'e taşındı; get_dashboard_data artık
        # ham cursor kullanmaz. result tuple'ının sırası korunur (summary
        # fonksiyonları bu sıraya göre okur).
        with get_session() as session:
            result = session.query(
                func.count(),
                func.count(distinct(UsageLog.sender)),
                func.sum(UsageLog.prompt_tokens),
                func.sum(UsageLog.completion_tokens),
                func.sum(UsageLog.total_tokens),
                func.sum(UsageLog.cost),
                func.avg(UsageLog.response_time),
            ).one()

        charts = {
            "daily_trend": _get_daily_trend(),
            "hourly_activity": _get_hourly_activity(),
            "model_distribution": _get_model_distribution(),
            "top_customers": _get_top_customers()
        }

        recent_activity = _get_recent_activity()

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

    try:

        # Faz 0: ham SQL'den ORM'e. Sözleşme birebir korunur:
        # sender bazında grupla, en son mesaj zamanına göre sırala, her satırda
        # mesaj sayısı + müşteri adı + son mesaj özeti. SUBSTRING(...,1,80) yerine
        # tam içerik çekilip Python'da [:80] kesilir (dialect-bağımsız, aynı sonuç).
        with get_session() as session:

            total = session.query(
                func.count(distinct(Conversation.sender))
            ).scalar() or 0

            # Her sender için en son mesajın içeriği (ilişkili/correlated alt sorgu)
            c2 = Conversation.__table__.alias("c2")
            last_content_subq = (
                select(c2.c.content)
                .where(c2.c.sender == Conversation.sender)
                .order_by(c2.c.timestamp.desc(), c2.c.id.desc())
                .limit(1)
                .scalar_subquery()
            )

            rows = (
                session.query(
                    Conversation.sender,
                    func.max(Customer.ad_soyad),
                    func.count(),
                    func.max(Conversation.timestamp),
                    last_content_subq,
                )
                .outerjoin(Customer, Customer.phone == Conversation.sender)
                .group_by(Conversation.sender)
                .order_by(func.max(Conversation.timestamp).desc())
                .limit(page_size)
                .offset(offset)
                .all()
            )

        items = [
            {
                "sender": sender,
                "ad_soyad": ad_soyad,
                "msg_count": msg_count or 0,
                "last_time": last_time.strftime("%Y-%m-%d %H:%M") if last_time else None,
                "last_content": (last_content or "")[:80]
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


def get_conversation_detail(sender, page=1, page_size=50):
    """Tek bir müşterinin mesaj geçmişi (sayfalı).

    Sayfa 1 en YENİ mesajları içerir; sayfa içinde kronolojik (eski->yeni)
    sıralanır. 'Daha eski' için sonraki sayfalara gidilir.
    """
    page, page_size, offset = _paginate(page, page_size)

    try:

        # Faz 0: bu okuma yolu ham SQL'den ORM'e taşındı. Çıktı sözleşmesi
        # (anahtarlar, tarih biçimi, sıralama) birebir korunur; panel değişmez.
        with get_session() as session:

            customer = (
                session.query(Customer)
                .filter(Customer.phone == sender)
                .first()
            )
            ad_soyad = customer.ad_soyad if customer else None

            total = (
                session.query(Conversation)
                .filter(Conversation.sender == sender)
                .count()
            )

            rows = (
                session.query(
                    Conversation.direction,
                    Conversation.content,
                    Conversation.timestamp,
                )
                .filter(Conversation.sender == sender)
                .order_by(Conversation.timestamp.desc(), Conversation.id.desc())
                .limit(page_size)
                .offset(offset)
                .all()
            )

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


def get_customers_list(page=1, page_size=50):
    """Sipariş vermiş müşteri listesi + sipariş özeti (sayfalı).

    Her satır: telefon, ad_soyad, ilk/son görülme, sipariş sayısı (is_update=0
    gerçek siparişler), son sipariş zamanı. En son aktif müşteri en üstte.
    """
    page, page_size, offset = _paginate(page, page_size)

    try:

        # Faz 0: ham SQL'den ORM'e. customers LEFT JOIN orders; gerçek sipariş
        # sayısı is_update=0 satırlardan CASE ile sayılır. Sözleşme korunur.
        with get_session() as session:

            total = session.query(Customer).count()

            rows = (
                session.query(
                    Customer.phone,
                    Customer.ad_soyad,
                    Customer.first_seen,
                    Customer.last_seen,
                    func.count(case((Order.is_update == 0, 1))),
                    func.max(Order.timestamp),
                )
                .outerjoin(Order, Order.customer_phone == Customer.phone)
                .group_by(
                    Customer.phone,
                    Customer.ad_soyad,
                    Customer.first_seen,
                    Customer.last_seen,
                )
                .order_by(Customer.last_seen.desc())
                .limit(page_size)
                .offset(offset)
                .all()
            )

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


def get_customer_detail(phone, page=1, page_size=50):
    """Tek bir müşterinin sipariş geçmişi (sayfalı, yeni->eski).

    Her satır bir sipariş ya da güncellemedir (is_update ile işaretli).
    """
    page, page_size, offset = _paginate(page, page_size)

    try:

        # Faz 0: ham SQL'den ORM'e. Müşteri bilgisi + sipariş geçmişi (yeni->eski).
        with get_session() as session:

            customer = (
                session.query(Customer)
                .filter(Customer.phone == phone)
                .first()
            )
            ad_soyad = customer.ad_soyad if customer else None
            first_seen = (
                customer.first_seen.strftime("%Y-%m-%d %H:%M")
                if (customer and customer.first_seen) else None
            )
            last_seen = (
                customer.last_seen.strftime("%Y-%m-%d %H:%M")
                if (customer and customer.last_seen) else None
            )

            total = (
                session.query(Order)
                .filter(Order.customer_phone == phone)
                .count()
            )

            rows = (
                session.query(
                    Order.timestamp,
                    Order.urun,
                    Order.renk,
                    Order.beden,
                    Order.adet,
                    Order.odeme_sekli,
                    Order.teslimat_adresi,
                    Order.is_update,
                )
                .filter(Order.customer_phone == phone)
                .order_by(Order.timestamp.desc(), Order.id.desc())
                .limit(page_size)
                .offset(offset)
                .all()
            )

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

    try:

        # Faz 0: 4 usage_logs sorgusu da ORM'e taşındı; tek oturumda çalışır.
        start = (
            datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=AI_USAGE_TREND_DAYS - 1)
        )

        with get_session() as session:

            # Genel özet
            r = session.query(
                func.count(),
                func.sum(UsageLog.prompt_tokens),
                func.sum(UsageLog.completion_tokens),
                func.sum(UsageLog.total_tokens),
                func.sum(UsageLog.cost),
                func.avg(UsageLog.response_time),
            ).one()

            # Model bazlı kırılım (maliyete göre azalan)
            model_rows = (
                session.query(
                    UsageLog.model,
                    func.count(),
                    func.sum(UsageLog.prompt_tokens),
                    func.sum(UsageLog.completion_tokens),
                    func.sum(UsageLog.total_tokens),
                    func.sum(UsageLog.cost),
                    func.avg(UsageLog.response_time),
                )
                .group_by(UsageLog.model)
                .order_by(func.sum(UsageLog.cost).desc())
                .all()
            )

            # Günlük trend (son AI_USAGE_TREND_DAYS gün)
            day_rows = (
                session.query(
                    func.date(UsageLog.timestamp),
                    func.count(),
                    func.sum(UsageLog.cost),
                    func.avg(UsageLog.response_time),
                )
                .filter(UsageLog.timestamp >= start)
                .group_by(func.date(UsageLog.timestamp))
                .order_by(func.date(UsageLog.timestamp))
                .all()
            )

            # Maliyete göre en yoğun 10 müşteri
            top_rows = (
                session.query(
                    UsageLog.sender,
                    func.count(),
                    func.sum(UsageLog.cost),
                )
                .group_by(UsageLog.sender)
                .order_by(func.sum(UsageLog.cost).desc())
                .limit(10)
                .all()
            )

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

        by_model = []
        for model, req, pt, ct, tt, cost, art in model_rows:
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

        by_day = {
            str(d): (req or 0, round(cost or 0, 6), round(art or 0, 3))
            for d, req, cost, art in day_rows
        }

        labels, d_cost, d_art, d_req = [], [], [], []
        for i in range(AI_USAGE_TREND_DAYS):
            key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            req, cost, art = by_day.get(key, (0, 0, 0))
            labels.append(key)
            d_req.append(req)
            d_cost.append(cost)
            d_art.append(art)

        top_customers = [
            {"sender": s, "requests": req or 0, "cost_usd": round(cost or 0, 6)}
            for s, req, cost in top_rows
        ]

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

    try:

        # Faz 0: 3 tablo (usage_logs, orders, conversations) üzerindeki 4 rapor
        # sorgusu ORM'e taşındı. CASE/COALESCE/NULLIF/TRIM SQLAlchemy func ile
        # dialect-bağımsız yazıldı. Sözleşme birebir korunur.
        with get_session() as session:

            # --- AI kullanımı ---
            a = (
                session.query(
                    func.count(),
                    func.sum(UsageLog.prompt_tokens),
                    func.sum(UsageLog.completion_tokens),
                    func.sum(UsageLog.total_tokens),
                    func.sum(UsageLog.cost),
                    func.avg(UsageLog.response_time),
                )
                .filter(UsageLog.timestamp >= start_dt, UsageLog.timestamp < end_ex)
                .one()
            )

            # --- Siparişler (gerçek sipariş vs güncelleme ayrımı) ---
            o = (
                session.query(
                    func.count(case((Order.is_update == 0, 1))),
                    func.count(case((Order.is_update == 1, 1))),
                    func.sum(case((Order.is_update == 0, Order.adet))),
                )
                .filter(Order.timestamp >= start_dt, Order.timestamp < end_ex)
                .one()
            )

            # Ödeme şekli dağılımı (yalnız gerçek siparişler)
            payment_label = func.coalesce(
                func.nullif(func.trim(Order.odeme_sekli), ""), "Belirtilmemiş"
            )
            payment_rows = (
                session.query(payment_label, func.count())
                .filter(
                    Order.is_update == 0,
                    Order.timestamp >= start_dt,
                    Order.timestamp < end_ex,
                )
                .group_by(payment_label)
                .order_by(func.count().desc())
                .all()
            )

            # --- Mesajlar ---
            m = (
                session.query(
                    func.count(case((Conversation.direction == "gelen", 1))),
                    func.count(case((Conversation.direction == "giden", 1))),
                    func.count(distinct(Conversation.sender)),
                )
                .filter(
                    Conversation.timestamp >= start_dt,
                    Conversation.timestamp < end_ex,
                )
                .one()
            )

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

        orders = {
            "count": o[0] or 0,
            "update_count": o[1] or 0,
            "total_quantity": int(o[2] or 0)
        }
        orders["by_payment"] = [
            {"odeme_sekli": p, "count": c or 0}
            for p, c in payment_rows
        ]

        messages = {
            "incoming": m[0] or 0,
            "outgoing": m[1] or 0,
            "unique_customers": m[2] or 0
        }

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
