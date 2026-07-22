from datetime import datetime

from Services.db import get_session
from Services.models import Conversation


def log_message(sender, direction, content):
    """Bir WhatsApp mesajını conversations tablosuna yazar (ORM).

    direction: 'gelen' (müşteriden) | 'giden' (bottan müşteriye).
    Loglama hatası ana akışı (webhook) kesmesin diye tüm hatalar yutulur.

    Faz 0 pilotu: bu fonksiyon ham SQL'den SQLAlchemy ORM'e taşınan ilk
    yazma yoludur. get_session context'i commit/rollback/close işini üstlenir.
    conversations tablosunun OKUMA tarafı (dashboard_service) bir sonraki
    adımda taşınacaktır; iki taraf da aynı tabloya erişir.
    """
    try:

        with get_session() as session:
            session.add(
                Conversation(
                    timestamp=datetime.now(),
                    sender=sender,
                    direction=direction,
                    content=str(content or ""),
                )
            )

    except Exception as e:

        print("🔴 log_message hatası:", e)
