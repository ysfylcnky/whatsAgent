"""Panelden düzenlenebilen anahtar-değer ayarları (settings tablosu).

config.py bu servisi öncelikli kaynak olarak okur; kayıt yoksa .env / kod
varsayılanına düşülür. Okuma fonksiyonları DB erişilemezse uygulamayı
çökertmez (hata yutulur, boş/None döner). Yazma fonksiyonu ise sonucu
(başarılı/başarısız) döndürür ki panel kullanıcıya durum gösterebilsin.
"""

from datetime import datetime

from Services.usage_logger import get_connection


def get_all_stored_settings():
    """settings tablosundaki tüm kayıtları {skey: svalue} olarak döndürür."""
    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute("SELECT skey, svalue FROM settings")

        rows = cursor.fetchall()

        cursor.close()

        return {k: v for k, v in rows}

    except Exception as e:

        print("🔴 get_all_stored_settings hatası:", e)

        return {}

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_stored_setting(key):
    """Tek bir ayarın DB'deki değerini döndürür (yoksa/erişilemezse None)."""
    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            "SELECT svalue FROM settings WHERE skey = %s",
            (key,)
        )

        row = cursor.fetchone()

        cursor.close()

        return row[0] if row else None

    except Exception as e:

        print("🔴 get_stored_setting hatası:", e)

        return None

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def save_stored_settings(mapping):
    """Verilen {skey: svalue} eşlemesini UPSERT eder. Başarıda True döner.

    Boş string değer kaydı, ilgili ayarın .env/varsayılana düşmesi anlamına
    gelir (config tarafında boş değer 'yok' sayılır).
    """
    if not mapping:
        return True

    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        now = datetime.now()

        for skey, svalue in mapping.items():
            cursor.execute(
                """
                INSERT INTO settings (skey, svalue, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE svalue = VALUES(svalue), updated_at = VALUES(updated_at)
                """,
                (skey, svalue, now)
            )

        conn.commit()

        cursor.close()

        return True

    except Exception as e:

        print("🔴 save_stored_settings hatası:", e)

        return False

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
