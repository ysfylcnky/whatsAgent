"""debug_faz1_tenant.py — Faz 1 tenant migration'ının izole doğrulaması (SQLite).

Bu script CANLI MySQL'e DOKUNMAZ. Geçici bir SQLite dosyasında ESKİ şemayı
(tenant_id'siz 5 tablo) kurar, örnek veriyle doldurur, ardından GERÇEK
`migrate_faz1_tenant.run_migration()` fonksiyonunu çağırır ve şunları kanıtlar:

  * tenants + users tabloları oluştu, varsayılan Mumi (id=1) eklendi.
  * 5 tablonun her birine tenant_id sütunu + index eklendi.
  * Mevcut satır sayıları KORUNDU (additive; veri kaybı yok).
  * Tüm eski satırlar backfill ile tenant_id=1 oldu.
  * Migration IDEMPOTENT: ikinci çalıştırma veriyi/tenant'ı çoğaltmaz.

Çalıştırma:  python debug_faz1_tenant.py   (proje kök dizininden)
"""

import os
import sys
import tempfile

from sqlalchemy import create_engine, inspect, text

# Migration ve modeller gerçek koddan gelir (davranış birebir aynı sınanır).
from migrate_faz1_tenant import run_migration, TARGET_TABLES, DEFAULT_TENANT_ID

_passed = 0
_failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  OK  {name}")
    else:
        _failed += 1
        print(f"  XX  {name}")


# ----------------------------------------------------------------------
# ESKİ şema (tenant_id'siz) — bugünkü production tablolarını yansıtır.
# ----------------------------------------------------------------------
_OLD_SCHEMA = {
    "usage_logs": """
        CREATE TABLE usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL, sender VARCHAR(32) NOT NULL,
            model VARCHAR(64) NOT NULL, prompt_tokens INT NOT NULL,
            completion_tokens INT NOT NULL, total_tokens INT NOT NULL,
            cost DOUBLE NOT NULL, response_time DOUBLE NOT NULL
        )""",
    "conversations": """
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL, sender VARCHAR(32) NOT NULL,
            direction VARCHAR(8) NOT NULL, content TEXT
        )""",
    "customers": """
        CREATE TABLE customers (
            phone VARCHAR(32) PRIMARY KEY, ad_soyad VARCHAR(255),
            first_seen DATETIME NOT NULL, last_seen DATETIME NOT NULL
        )""",
    "orders": """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL, customer_phone VARCHAR(32) NOT NULL,
            ad_soyad VARCHAR(255), telefon VARCHAR(64), teslimat_adresi TEXT,
            urun VARCHAR(255), renk VARCHAR(128), beden VARCHAR(128), adet INT,
            odeme_sekli VARCHAR(64), is_update TINYINT NOT NULL DEFAULT 0
        )""",
    "settings": """
        CREATE TABLE settings (
            skey VARCHAR(64) PRIMARY KEY, svalue TEXT, updated_at DATETIME NOT NULL
        )""",
}

# Her tabloya kaç örnek satır basılacağı (backfill'i anlamlı kılmak için).
_SEED = {
    "usage_logs": [
        "INSERT INTO usage_logs (timestamp, sender, model, prompt_tokens, completion_tokens, total_tokens, cost, response_time) "
        "VALUES ('2026-07-01 10:00:00','905551112233','gpt-4.1-mini',100,50,150,0.0012,1.2)",
        "INSERT INTO usage_logs (timestamp, sender, model, prompt_tokens, completion_tokens, total_tokens, cost, response_time) "
        "VALUES ('2026-07-01 11:00:00','905554445566','gpt-4.1',200,80,280,0.004,2.1)",
    ],
    "conversations": [
        "INSERT INTO conversations (timestamp, sender, direction, content) "
        "VALUES ('2026-07-01 10:00:00','905551112233','gelen','M beden var mi? ğüşıöç')",
        "INSERT INTO conversations (timestamp, sender, direction, content) "
        "VALUES ('2026-07-01 10:00:05','905551112233','giden','Evet mevcut')",
    ],
    "customers": [
        "INSERT INTO customers (phone, ad_soyad, first_seen, last_seen) "
        "VALUES ('905551112233','Ali Veli','2026-06-01 09:00:00','2026-07-01 10:00:00')",
    ],
    "orders": [
        "INSERT INTO orders (timestamp, customer_phone, ad_soyad, telefon, teslimat_adresi, urun, renk, beden, adet, odeme_sekli, is_update) "
        "VALUES ('2026-07-01 10:05:00','905551112233','Ali Veli','05321112233','Istanbul','Elbise','Kirmizi','M',2,'Havale',0)",
        "INSERT INTO orders (timestamp, customer_phone, ad_soyad, telefon, teslimat_adresi, urun, renk, beden, adet, odeme_sekli, is_update) "
        "VALUES ('2026-07-01 10:10:00','905551112233','Ali Veli','05321112233','Istanbul','Elbise','Kirmizi','L',3,'Havale',1)",
    ],
    "settings": [
        "INSERT INTO settings (skey, svalue, updated_at) VALUES ('STORE_IBAN','TR12','2026-07-01 09:00:00')",
        "INSERT INTO settings (skey, svalue, updated_at) VALUES ('STORE_IBAN_NAME','Mumi','2026-07-01 09:00:00')",
    ],
}


def _row_count(engine, table):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _null_tenant_count(engine, table):
    with engine.connect() as conn:
        return conn.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
        ).scalar()


def main():
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    engine = create_engine(f"sqlite:///{tmp.name}", future=True)

    # --- ESKİ şemayı kur + veriyle doldur ---
    with engine.begin() as conn:
        for ddl in _OLD_SCHEMA.values():
            conn.execute(text(ddl))
        for stmts in _SEED.values():
            for s in stmts:
                conn.execute(text(s))

    before_counts = {t: _row_count(engine, t) for t in TARGET_TABLES}

    print("== migration (1. calisma) ==")
    run_migration(engine)

    insp = inspect(engine)
    db_tables = set(insp.get_table_names())

    print("\n== yeni tablolar ==")
    check("tenants tablosu olustu", "tenants" in db_tables)
    check("users tablosu olustu", "users" in db_tables)

    with engine.connect() as conn:
        trow = conn.execute(
            text("SELECT id, name, status FROM tenants WHERE id = :t"),
            {"t": DEFAULT_TENANT_ID},
        ).first()
    check("varsayilan tenant id=1 var", trow is not None)
    check("tenant adi 'Mumi'", trow is not None and trow[1] == "Mumi")
    check("tenant status 'active'", trow is not None and trow[2] == "active")

    print("\n== 5 tabloda tenant_id sutunu + index ==")
    for t in TARGET_TABLES:
        cols = {c["name"] for c in insp.get_columns(t)}
        check(f"[{t}] tenant_id sutunu eklendi", "tenant_id" in cols)
        idx_names = {ix.get("name") for ix in insp.get_indexes(t)}
        check(f"[{t}] tenant_id index'i var", f"ix_{t}_tenant_id" in idx_names)

    print("\n== veri korundu + backfill ==")
    for t in TARGET_TABLES:
        after = _row_count(engine, t)
        check(f"[{t}] satir sayisi korundu ({before_counts[t]})", after == before_counts[t])
        check(f"[{t}] NULL tenant_id kalmadi", _null_tenant_count(engine, t) == 0)

    # Türkçe içerik hâlâ bozulmamış mı (veri kaybı/bozulması yok)?
    with engine.connect() as conn:
        content = conn.execute(
            text("SELECT content FROM conversations WHERE direction='gelen'")
        ).scalar()
    check("Turkce icerik korundu", content is not None and content.endswith("ğüşıöç"))

    print("\n== idempotency (2. calisma) ==")
    run_migration(engine)
    with engine.connect() as conn:
        tenant_count = conn.execute(text("SELECT COUNT(*) FROM tenants")).scalar()
    check("tekrar calistirma tenant'i cogaltmadi (1 kayit)", tenant_count == 1)
    for t in TARGET_TABLES:
        check(f"[{t}] satir sayisi hala sabit", _row_count(engine, t) == before_counts[t])

    try:
        os.unlink(tmp.name)
    except OSError:
        pass

    print(f"\nSONUC: {_passed} gecti, {_failed} kaldi")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
