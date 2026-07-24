"""Panelden düzenlenebilen anahtar-değer ayarları (settings tablosu).

config.py bu servisi öncelikli kaynak olarak okur; kayıt yoksa .env / kod
varsayılanına düşülür. Okuma fonksiyonları DB erişilemezse uygulamayı
çökertmez (hata yutulur, boş/None döner). Yazma fonksiyonu ise sonucu
(başarılı/başarısız) döndürür ki panel kullanıcıya durum gösterebilsin.
"""

from datetime import datetime

from sqlalchemy import select

from Services.db import get_session
from Services.models import Setting


def get_all_stored_settings():
    """settings tablosundaki tüm kayıtları {skey: svalue} olarak döndürür (ORM)."""
    try:

        with get_session() as session:

            rows = session.execute(
                select(Setting.skey, Setting.svalue)
            ).all()

            return {k: v for k, v in rows}

    except Exception as e:

        print("🔴 get_all_stored_settings hatası:", e)

        return {}


def get_stored_setting(key):
    """Tek bir ayarın DB'deki değerini döndürür (yoksa/erişilemezse None) — ORM."""
    try:

        with get_session() as session:

            row = session.get(Setting, key)

            return row.svalue if row else None

    except Exception as e:

        print("🔴 get_stored_setting hatası:", e)

        return None


def save_stored_settings(mapping):
    """Verilen {skey: svalue} eşlemesini UPSERT eder (ORM). Başarıda True döner.

    Boş string değer kaydı, ilgili ayarın .env/varsayılana düşmesi anlamına
    gelir (config tarafında boş değer 'yok' sayılır). Upsert semantiği korunur:
    anahtar yoksa eklenir, varsa svalue ve updated_at güncellenir.
    """
    if not mapping:
        return True

    try:

        now = datetime.now()

        with get_session() as session:

            for skey, svalue in mapping.items():

                obj = session.get(Setting, skey)

                if obj is None:
                    session.add(
                        Setting(skey=skey, svalue=svalue, updated_at=now)
                    )
                else:
                    obj.svalue = svalue
                    obj.updated_at = now

        return True

    except Exception as e:

        print("🔴 save_stored_settings hatası:", e)

        return False
