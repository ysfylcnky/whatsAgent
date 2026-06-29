import mysql.connector
from mysql.connector import pooling
from datetime import datetime
from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)

# Tüm bağlantılar tek bir havuzdan yönetilir.
# Havuz ilk ihtiyaç anında (lazy) kurulur.
_pool = None


def _get_pool():
    """Bağlantı havuzunu tek seferlik kurar ve döndürür."""
    global _pool

    if _pool is None:

        _pool = pooling.MySQLConnectionPool(
            pool_name="usage_pool",
            pool_size=5,
            pool_reset_session=True,
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            autocommit=False,
        )

    return _pool


def get_connection():
    """Havuzdan bir bağlantı verir.

    Çağıran kod iş bitince conn.close() ile bağlantıyı havuza geri bırakmalı.
    """
    return _get_pool().get_connection()


def initialize_database():
    """Veritabanı ve tablo yoksa oluşturur.

    MySQL'e bağlanılamazsa uygulamayı çökertmez; sadece hatayı loglar.
    """
    try:

        # Önce veritabanını oluştur (database parametresi olmadan sunucuya bağlan)
        server_conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
        )

        server_cursor = server_conn.cursor()

        server_cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )

        server_conn.commit()
        server_cursor.close()
        server_conn.close()

        # Tabloyu havuzdan alınan bağlantı ile oluştur
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                sender VARCHAR(32) NOT NULL,
                model VARCHAR(64) NOT NULL,
                prompt_tokens INT NOT NULL,
                completion_tokens INT NOT NULL,
                total_tokens INT NOT NULL,
                cost DOUBLE NOT NULL,
                response_time DOUBLE NOT NULL,
                INDEX idx_timestamp (timestamp),
                INDEX idx_sender (sender)
            )
        """)

        conn.commit()
        cursor.close()
        conn.close()

        print("🟢 MySQL veritabanı/tablo hazır.")

    except Exception as e:

        print("🔴 MySQL initialize_database hatası:", e)


def log_usage(
    sender,
    model,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    cost,
    response_time
):
    """Tek bir OpenAI çağrısının kullanım bilgisini kaydeder.

    Loglama hatası yanıt akışını (webhook) kesmesin diye tüm hatalar yutulur.
    """
    conn = None

    try:

        conn = get_connection()

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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                datetime.now(),
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
        cursor.close()

    except Exception as e:

        print("🔴 log_usage hatası:", e)

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_total_requests():

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM usage_logs"
        )

        total = cursor.fetchone()[0]

        cursor.close()

        return total or 0

    except Exception as e:

        print("🔴 get_total_requests hatası:", e)

        return 0

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_total_tokens():

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT SUM(total_tokens) FROM usage_logs"
        )

        total = cursor.fetchone()[0]

        cursor.close()

        # MySQL SUM(INT) -> Decimal döner; orijinal int dönüş tipini koru
        return int(total or 0)

    except Exception as e:

        print("🔴 get_total_tokens hatası:", e)

        return 0

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_total_cost():

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT SUM(cost) FROM usage_logs"
        )

        total = cursor.fetchone()[0]

        cursor.close()

        return round(total or 0, 6)

    except Exception as e:

        print("🔴 get_total_cost hatası:", e)

        return 0

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_average_response_time():

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT AVG(response_time) FROM usage_logs"
        )

        average = cursor.fetchone()[0]

        cursor.close()

        return round(average or 0, 3)

    except Exception as e:

        print("🔴 get_average_response_time hatası:", e)

        return 0

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_usage_summary():

    conn = None

    try:

        conn = get_connection()

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

        cursor.close()

        return {

            "total_requests": result[0] or 0,

            # MySQL SUM(INT) -> Decimal döner; orijinal int dönüş tipini koru
            "total_tokens": int(result[1] or 0),

            "total_cost": round(result[2] or 0, 6),

            "average_response_time": round(result[3] or 0, 3)

        }

    except Exception as e:

        print("🔴 get_usage_summary hatası:", e)

        return {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0,
            "average_response_time": 0
        }

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
