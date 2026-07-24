"""debug_faz0_writes.py — Faz 0 yazma yollarının ORM doğrulaması (izole SQLite).

Bu script CANLI MySQL'e DOKUNMAZ. Services.db'nin engine/SessionLocal'ını
geçici bir SQLite dosyasına yönlendirir, şemayı ORM modellerinden kurar ve
Faz 0'da ORM'e taşınan yazma fonksiyonlarını (log_usage, save_order + customers
upsert, settings CRUD) GERÇEK fonksiyonları çağırarak doğrular.

Amaç: davranışın (upsert, first_seen korunması, is_update geçmişi, hata yutma)
ham SQL sürümüyle birebir aynı kaldığını kanıtlamak.

Çalıştırma:  python debug_faz0_writes.py   (proje kök dizininden)
"""

import os
import sys
import time
import tempfile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Engine'i geçici SQLite'a çevir — Services.db import edilince MySQL engine'i
# kurulur ama bağlanmaz (lazy); biz kullanılmadan önce SQLite ile değiştiriyoruz.
import Services.db as db
from Services.db import Base
from Services.models import UsageLog, Customer, Order, Setting  # Base.metadata'ya kaydolur

# SQLite, MySQL'e özgü TINYINT tipini derleyemez. Bu YALNIZCA test şeması içindir;
# production modelleri (MySQL) değişmez. TINYINT'i SQLite'ta INTEGER'a eşle.
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.mysql import TINYINT as _MYSQL_TINYINT


@compiles(_MYSQL_TINYINT, "sqlite")
def _tinyint_as_integer_on_sqlite(element, compiler, **kw):
    return "INTEGER"

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp.close()
_test_engine = create_engine(f"sqlite:///{_tmp.name}", future=True)

db.engine = _test_engine
db.SessionLocal = sessionmaker(
    bind=_test_engine, autoflush=False, expire_on_commit=False, future=True
)

Base.metadata.create_all(_test_engine)

# Fonksiyonlar get_session -> db.SessionLocal'ı çağrı anında okur; patch görülür.
from Services.usage_logger import log_usage
from Services.order_service import save_order
from Services.settings_service import (
    get_all_stored_settings,
    get_stored_setting,
    save_stored_settings,
)

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


def fresh():
    return db.SessionLocal()


print("== log_usage (usage_logs INSERT) ==")
log_usage("905551112233", "gpt-4.1-mini", 100, 50, 150, 0.0012, 1.234)
with fresh() as s:
    rows = s.execute(select(UsageLog)).scalars().all()
check("1 usage_logs satırı yazıldı", len(rows) == 1)
check("total_tokens=150", bool(rows) and rows[0].total_tokens == 150)
check("cost korunur", bool(rows) and abs(rows[0].cost - 0.0012) < 1e-9)

print("== save_order (yeni müşteri + sipariş) ==")
order1 = {
    "ad_soyad": "Ali Veli", "telefon": "05321112233", "teslimat_adresi": "İstanbul",
    "urun": "Elbise", "renk": "Kırmızı", "beden": "M", "adet": 2, "odeme_sekli": "Havale",
}
save_order("905551112233", order1, is_update=False)
with fresh() as s:
    custs = s.execute(select(Customer)).scalars().all()
    ords = s.execute(select(Order)).scalars().all()
check("1 müşteri oluştu", len(custs) == 1)
check("1 sipariş satırı", len(ords) == 1)
check("is_update=0", bool(ords) and int(ords[0].is_update) == 0)
check("adet=2", bool(ords) and ords[0].adet == 2)
first_seen_before = custs[0].first_seen if custs else None

print("== save_order (UPSERT: aynı müşteri, güncelleme) ==")
time.sleep(0.01)
order2 = dict(order1)
order2["ad_soyad"] = "Ali Veli Guncel"
order2["adet"] = 3
save_order("905551112233", order2, is_update=True)
with fresh() as s:
    custs = s.execute(select(Customer)).scalars().all()
    ords = s.execute(select(Order).order_by(Order.id)).scalars().all()
check("müşteri hâlâ 1 (upsert)", len(custs) == 1)
check("ad_soyad güncellendi", bool(custs) and custs[0].ad_soyad == "Ali Veli Guncel")
check("first_seen KORUNDU (upsert'te değişmez)", bool(custs) and custs[0].first_seen == first_seen_before)
check("2 sipariş satırı (geçmiş korunur)", len(ords) == 2)
check("ikinci satır is_update=1", len(ords) == 2 and int(ords[1].is_update) == 1)

print("== settings CRUD (Setting UPSERT/SELECT) ==")
ok = save_stored_settings({"STORE_IBAN": "TR12", "STORE_IBAN_NAME": "Mumi"})
check("save True döner", ok is True)
check("get_stored_setting tek değer", get_stored_setting("STORE_IBAN") == "TR12")
alls = get_all_stored_settings()
check("get_all 2 kayıt", alls.get("STORE_IBAN") == "TR12" and alls.get("STORE_IBAN_NAME") == "Mumi")
save_stored_settings({"STORE_IBAN": "TR99"})
check("upsert güncelleme (yeni satır değil)", get_stored_setting("STORE_IBAN") == "TR99" and len(get_all_stored_settings()) == 2)
check("boş mapping True döner", save_stored_settings({}) is True)
check("olmayan anahtar None", get_stored_setting("YOK_BOYLE") is None)

try:
    os.unlink(_tmp.name)
except OSError:
    pass

print(f"\nSONUC: {_passed} gecti, {_failed} kaldi")
sys.exit(1 if _failed else 0)
