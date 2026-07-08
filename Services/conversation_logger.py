from datetime import datetime
from Services.usage_logger import get_connection


def log_message(sender, direction, content):
    """Bir WhatsApp mesajını conversations tablosuna yazar.

    direction: 'gelen' (müşteriden) | 'giden' (bottan müşteriye).
    Loglama hatası ana akışı (webhook) kesmesin diye tüm hatalar yutulur.
    """
    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO conversations (
                timestamp,
                sender,
                direction,
                content
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                datetime.now(),
                sender,
                direction,
                str(content or "")
            )
        )

        conn.commit()
        cursor.close()

    except Exception as e:

        print("🔴 log_message hatası:", e)

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
