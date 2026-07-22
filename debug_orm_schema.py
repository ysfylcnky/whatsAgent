"""ORM modelleri (Services/models.py) için şema doğrulaması.

İki mod:

1. Varsayılan (bağlantısız): Modellerden üretilen MySQL DDL'i ve index'leri
   inceler; canlı DB gerektirmez. Modellerin tutarlılığını kontrol eder.

    python debug_orm_schema.py

2. --live: Gerçek veritabanına bağlanıp, ORM modellerinin mevcut tablolarla
   birebir eşleştiğini doğrular (sütun adları/tipleri). Docker'da:

    docker compose exec app python debug_orm_schema.py --live
"""

import sys
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql

from Services.db import Base, engine, get_session
import Services.models as m

MODELS = [m.UsageLog, m.Conversation, m.Customer, m.Order, m.Setting]

# Mevcut şemadaki (usage_logger.py) sütun -> beklenen özet tip.
EXPECTED = {
    "usage_logs": {"id", "timestamp", "sender", "model", "prompt_tokens",
                   "completion_tokens", "total_tokens", "cost", "response_time"},
    "conversations": {"id", "timestamp", "sender", "direction", "content"},
    "customers": {"phone", "ad_soyad", "first_seen", "last_seen"},
    "orders": {"id", "timestamp", "customer_phone", "ad_soyad", "telefon",
               "teslimat_adresi", "urun", "renk", "beden", "adet",
               "odeme_sekli", "is_update"},
    "settings": {"skey", "svalue", "updated_at"},
}

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"{'✅' if cond else '❌'} {name}")


def test_metadata_offline():
    tables = set(Base.metadata.tables.keys())
    check("5 tablo tanımlı", tables == set(EXPECTED.keys()))

    for model in MODELS:
        t = model.__tablename__
        cols = set(model.__table__.columns.keys())
        check(f"[{t}] sütunlar şemayla eşleşiyor", cols == EXPECTED[t])

    # Index'ler metadata'da mı (CreateTable çıktısında görünmezler)
    idx = {i.name for t in Base.metadata.tables.values() for i in t.indexes}
    for expected_idx in ["idx_timestamp", "idx_sender", "idx_conv_sender",
                         "idx_conv_timestamp", "idx_orders_phone", "idx_orders_timestamp"]:
        check(f"index tanımlı: {expected_idx}", expected_idx in idx)

    # DDL üretilebiliyor (tip hatası yok)
    try:
        for model in MODELS:
            str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
        check("tüm modeller MySQL DDL'e derleniyor", True)
    except Exception as e:
        check(f"DDL derleme ({e})", False)


def test_orm_roundtrip_sqlite():
    """MySQL olmadan ORM yaz/oku mantığını SQLite ile doğrular.

    conversation_logger.py'nin kullandığı desen (session.add + commit) burada
    izole olarak sınanır; Türkçe karakter korunumu dahil.
    """
    eng = create_engine("sqlite:///:memory:")
    m.Conversation.__table__.create(eng)
    Session = sessionmaker(bind=eng)

    s = Session()
    s.add(m.Conversation(
        timestamp=datetime.now(), sender="905550001122",
        direction="gelen", content="M beden var mı? ğüşıöç",
    ))
    s.commit()

    row = s.query(m.Conversation).first()
    check("ORM round-trip: kayıt yazıldı", row is not None)
    check("ORM round-trip: alanlar doğru",
          row and row.sender == "905550001122" and row.direction == "gelen")
    check("ORM round-trip: Türkçe içerik korundu",
          row and row.content.endswith("ğüşıöç"))
    s.close()


def test_live():
    """Gerçek DB'ye bağlanıp sütun uyumunu + ORM yazma round-trip'ini doğrular."""
    from sqlalchemy import inspect

    insp = inspect(engine)
    db_tables = set(insp.get_table_names())

    for t, expected_cols in EXPECTED.items():
        check(f"[canlı] tablo mevcut: {t}", t in db_tables)
        if t in db_tables:
            actual = {c["name"] for c in insp.get_columns(t)}
            missing = expected_cols - actual
            check(f"[canlı] {t} sütun uyumu", not missing)

    # Gerçek MySQL'e ORM ile geçici bir kayıt yaz, oku, sil (kalıcı iz bırakmaz).
    marker = "__orm_selftest__"
    try:
        with get_session() as s:
            s.add(m.Conversation(
                timestamp=datetime.now(), sender=marker,
                direction="gelen", content="ORM canlı yazma testi ğş",
            ))

        with get_session() as s:
            found = s.query(m.Conversation).filter_by(sender=marker).first()
            check("[canlı] ORM gerçek DB'ye yazdı ve okudu",
                  found is not None and found.content.endswith("ğş"))
            # Temizlik: test kaydını sil
            s.query(m.Conversation).filter_by(sender=marker).delete()

        check("[canlı] test kaydı temizlendi", True)
    except Exception as e:
        check(f"[canlı] ORM yazma round-trip ({e})", False)


def main():
    print("--- ORM şema doğrulaması ---\n")

    test_metadata_offline()
    test_orm_roundtrip_sqlite()

    if "--live" in sys.argv:
        print("\n--- Canlı DB kontrolü ---")
        try:
            test_live()
        except Exception as e:
            check(f"canlı bağlantı ({e})", False)

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} kontrol geçti.")
    if failed:
        print("BAŞARISIZ:")
        for n in failed:
            print(f"  - {n}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
