"""migrate_faz1_tenant.py — Faz 1 tenant veri modeli migration'ı (additive).

Tek-kiracılı şemayı çok-kiracılıya taşır. TAMAMEN ADDITIVE ve IDEMPOTENT'tir:
tekrar çalıştırmak güvenlidir, mevcut veriyi bozmaz.

Yaptıkları (her adım "yoksa" mantığıyla):
  1. `tenants` + `users` tablolarını oluşturur.
  2. Varsayılan tenant'ı ekler: id=1, ad "Mumi" (mevcut tüm veri buna bağlanır).
  3. 5 mevcut tabloya (usage_logs, conversations, customers, orders, settings)
     `tenant_id` sütunu + index ekler; MySQL'de ayrıca FK constraint kurar.
  4. Mevcut satırların `tenant_id`'sini 1 (Mumi) ile doldurur (backfill).

Aynı fonksiyon (`run_migration(engine)`) hem canlı MySQL'de hem izole SQLite
testinde (debug_faz1_tenant.py) çalışacak şekilde dialect-bağımsız yazılmıştır.
SQLite ALTER ile FK eklemeyi desteklemediğinden fiziksel FK yalnız MySQL'de
kurulur (ORM modeli FK'yi zaten taşır).

ÖNCE YEDEK AL — şema değişikliğidir:
    ./backup_mysql.sh

Canlı çalıştırma (Docker):
    docker compose exec app python migrate_faz1_tenant.py
"""

from datetime import datetime

from sqlalchemy import inspect, text

from Services.db import Base  # noqa: F401  (Base.metadata için)
from Services.models import Tenant, User

# tenant_id eklenecek mevcut tablolar.
TARGET_TABLES = ["usage_logs", "conversations", "customers", "orders", "settings"]

DEFAULT_TENANT_ID = 1
DEFAULT_TENANT_NAME = "Mumi"


def _column_exists(insp, table, column):
    return any(c["name"] == column for c in insp.get_columns(table))


def _index_exists(insp, table, index_name):
    return any(ix.get("name") == index_name for ix in insp.get_indexes(table))


def _fk_on_column_exists(insp, table, column):
    for fk in insp.get_foreign_keys(table):
        if column in (fk.get("constrained_columns") or []):
            return True
    return False


def run_migration(engine):
    """Faz 1 şema geçişini verilen engine üzerinde idempotent uygular.

    Var olan tabloların tümü yerinde bırakılır; yalnız additive değişiklik
    yapılır. Her adımdan önce mevcut durum kontrol edilir, böylece script
    tekrar çalıştırılabilir.
    """
    dialect = engine.dialect.name

    # 1) tenants + users tabloları (yoksa). tenants önce (users FK'si ona bakar).
    Tenant.__table__.create(bind=engine, checkfirst=True)
    User.__table__.create(bind=engine, checkfirst=True)

    # 2) Varsayılan tenant (id=1, Mumi) — yoksa ekle.
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT id FROM tenants WHERE id = :tid"),
            {"tid": DEFAULT_TENANT_ID},
        ).first()
        if exists is None:
            conn.execute(
                text(
                    "INSERT INTO tenants (id, name, status, created_at) "
                    "VALUES (:tid, :name, 'active', :now)"
                ),
                {
                    "tid": DEFAULT_TENANT_ID,
                    "name": DEFAULT_TENANT_NAME,
                    "now": datetime.now(),
                },
            )
            print(f"  + tenants: varsayilan '{DEFAULT_TENANT_NAME}' (id={DEFAULT_TENANT_ID}) eklendi")
        else:
            print(f"  = tenants: id={DEFAULT_TENANT_ID} zaten var, dokunulmadi")

    # 3) 5 tabloya sütun + index (+ MySQL FK). Her kontrolden önce taze inspector.
    for table in TARGET_TABLES:
        # 3a) kolon
        insp = inspect(engine)
        if not _column_exists(insp, table, "tenant_id"):
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER"))
            print(f"  + {table}.tenant_id sutunu eklendi")
        else:
            print(f"  = {table}.tenant_id zaten var")

        # 3b) index — SQLAlchemy'nin ORM'de ürettiği adla ("ix_<tablo>_<sutun>")
        # aynı tutulur ki fresh (ORM) ve migrate edilmiş şema aynı ada sahip olsun.
        idx_name = f"ix_{table}_tenant_id"
        insp = inspect(engine)
        if not _index_exists(insp, table, idx_name):
            with engine.begin() as conn:
                conn.execute(text(f"CREATE INDEX {idx_name} ON {table} (tenant_id)"))
            print(f"  + {table} index '{idx_name}' olusturuldu")

        # 3c) FK — yalnız MySQL (SQLite ALTER ile FK eklemez; ORM modeli FK'yi taşır).
        if dialect == "mysql":
            insp = inspect(engine)
            if not _fk_on_column_exists(insp, table, "tenant_id"):
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_tenant "
                            f"FOREIGN KEY (tenant_id) REFERENCES tenants(id)"
                        )
                    )
                print(f"  + {table} FK (tenant_id -> tenants.id) eklendi")

    # 4) Backfill — NULL tenant_id'leri varsayılan tenant'a bağla.
    for table in TARGET_TABLES:
        with engine.begin() as conn:
            result = conn.execute(
                text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"),
                {"tid": DEFAULT_TENANT_ID},
            )
            print(f"  ~ {table}: {result.rowcount} satir tenant_id={DEFAULT_TENANT_ID} yapildi")


def verify(engine):
    """Migration sonrası NULL tenant_id kalmadığını raporlar (bilgi amaçlı)."""
    insp = inspect(engine)
    all_ok = True
    for table in TARGET_TABLES:
        if not _column_exists(insp, table, "tenant_id"):
            print(f"  XX {table}: tenant_id sutunu YOK")
            all_ok = False
            continue
        with engine.connect() as conn:
            nulls = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
            ).scalar()
        flag = "OK " if not nulls else "XX "
        if nulls:
            all_ok = False
        print(f"  {flag}{table}: NULL tenant_id = {nulls}")
    return all_ok


if __name__ == "__main__":
    print("=" * 60)
    print("Faz 1 tenant migration — CANLI MySQL")
    print("!! Once yedek al:  ./backup_mysql.sh")
    print("=" * 60)

    from Services.db import engine

    print("\n[1] Migration calisiyor...")
    run_migration(engine)

    print("\n[2] Dogrulama...")
    ok = verify(engine)

    print("\nSONUC:", "BASARILI" if ok else "EKSIK/HATA (yukariya bak)")
