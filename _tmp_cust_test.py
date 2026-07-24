import os
os.environ.update(MYSQL_USER='u',MYSQL_PASSWORD='p',MYSQL_HOST='h',MYSQL_DATABASE='d',MYSQL_PORT='3306')
from datetime import datetime
from sqlalchemy import create_engine, text, Integer
from sqlalchemy.orm import sessionmaker
from Services import db
from Services.models import Customer, Order
Order.__table__.c.is_update.type = Integer()  # TINYINT SQLite'ta yok

eng = create_engine("sqlite:///:memory:")
Customer.__table__.create(eng); Order.__table__.create(eng)
db.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)

with db.get_session() as s:
    s.add(Customer(phone="90111", ad_soyad="Ali Veli", first_seen=datetime(2026,6,1,10,0), last_seen=datetime(2026,7,3,10,0)))
    s.add(Customer(phone="90222", ad_soyad="Ayşe Şen", first_seen=datetime(2026,6,2,10,0), last_seen=datetime(2026,7,1,10,0)))
    s.add(Customer(phone="90333", ad_soyad=None, first_seen=datetime(2026,6,3,10,0), last_seen=datetime(2026,7,2,10,0)))
    def o(ph,upd,t): s.add(Order(customer_phone=ph, ad_soyad="x", telefon="x", teslimat_adresi="adres çğü", urun="Elbise", renk="Kırmızı", beden="M", adet=1, odeme_sekli="Havale", is_update=upd, timestamp=t))
    o("90111",0,datetime(2026,7,1,9,0)); o("90111",0,datetime(2026,7,2,9,0)); o("90111",1,datetime(2026,7,3,9,0))
    o("90222",0,datetime(2026,6,15,9,0))

res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")
from Services.dashboard_service import get_customers_list, get_customer_detail

cl = get_customers_list(page=1, page_size=50)
ck("toplam 3 müşteri", cl["total"]==3)
ck("sıralama last_seen DESC", [i["phone"] for i in cl["items"]]==["90111","90333","90222"])
byp={i["phone"]:i for i in cl["items"]}
ck("90111 gerçek sipariş=2 (güncelleme sayılmaz)", byp["90111"]["order_count"]==2)
ck("90222 sipariş=1", byp["90222"]["order_count"]==1)
ck("90333 sipariş=0", byp["90333"]["order_count"]==0)
ck("90333 ad_soyad None", byp["90333"]["ad_soyad"] is None)
ck("last_order_time biçimi", byp["90111"]["last_order_time"]=="2026-07-03 09:00")
with eng.connect() as conn:
    old={r[0]:r[1] for r in conn.execute(text("SELECT cu.phone, COUNT(CASE WHEN o.is_update=0 THEN 1 END) FROM customers cu LEFT JOIN orders o ON o.customer_phone=cu.phone GROUP BY cu.phone")).fetchall()}
ck("order_count ESKİ ile eşleşiyor", all(byp[p]["order_count"]==old[p] for p in old))

cd = get_customer_detail("90111", page=1, page_size=50)
ck("detail ad_soyad", cd["ad_soyad"]=="Ali Veli")
ck("detail toplam 3", cd["total"]==3)
ck("detail sıra yeni->eski", cd["orders"][0]["timestamp"]=="2026-07-03 09:00")
ck("detail is_update bool", cd["orders"][0]["is_update"]==True and cd["orders"][1]["is_update"]==False)
ck("detail Türkçe adres", cd["orders"][0]["teslimat_adresi"]=="adres çğü")
ck("detail izolasyon (sadece 90111)", cd["total"]==3)

fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
