import os
os.environ.update(MYSQL_USER='u',MYSQL_PASSWORD='p',MYSQL_HOST='h',MYSQL_DATABASE='d',MYSQL_PORT='3306')
from datetime import datetime
from sqlalchemy import create_engine, text, Integer
from sqlalchemy.orm import sessionmaker
from Services import db
from Services.models import UsageLog, Order
Order.__table__.c.is_update.type = Integer()

eng = create_engine("sqlite:///:memory:")
UsageLog.__table__.create(eng); Order.__table__.create(eng)
db.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)

inr = datetime(2026,7,15,10,30,45)
out = datetime(2026,6,1,10,0,0)
with db.get_session() as s:
    s.add(Order(customer_phone="90111",ad_soyad="Ali",telefon="555",teslimat_adresi="adres çğü",urun="Elbise",renk="Kırmızı",beden="M",adet=2,odeme_sekli="Havale",is_update=0,timestamp=inr))
    s.add(Order(customer_phone="90111",ad_soyad="Ali",telefon="555",teslimat_adresi="adres2",urun="Elbise",renk="Mavi",beden="L",adet=1,odeme_sekli="",is_update=1,timestamp=datetime(2026,7,16,11,0,0)))
    s.add(Order(customer_phone="90222",ad_soyad="Ayşe",telefon="666",teslimat_adresi="a",urun="Bluz",renk="Beyaz",beden="S",adet=3,odeme_sekli="Kapıda",is_update=0,timestamp=out))  # aralık dışı
    s.add(UsageLog(sender="90111",model="m",prompt_tokens=10,completion_tokens=20,total_tokens=30,cost=0.01,response_time=1.0,timestamp=inr))
    s.add(UsageLog(sender="90222",model="m",prompt_tokens=5,completion_tokens=5,total_tokens=10,cost=0.005,response_time=0.8,timestamp=inr))
    s.add(UsageLog(sender="90111",model="m",prompt_tokens=1,completion_tokens=1,total_tokens=2,cost=0.001,response_time=0.5,timestamp=out))  # dışı

from Services.dashboard_service import get_orders_export_rows, get_daily_usage_export_rows
orows = get_orders_export_rows("2026-07-01","2026-07-31")
drows = get_daily_usage_export_rows("2026-07-01","2026-07-31")

res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")
# orders export: aralık içi 2 satır (biri sipariş biri güncelleme), timestamp'e göre sıralı
ck("orders export 2 satır (aralık içi)", len(orows)==2)
ck("orders timestamp biçimi", orows[0][0]=="2026-07-15 10:30:45")
ck("orders is_update etiketi 'siparis'", orows[0][10]=="siparis")
ck("orders is_update etiketi 'guncelleme'", orows[1][10]=="guncelleme")
ck("orders Türkçe adres korundu", orows[0][9]=="adres çğü")
ck("orders adet sayı", orows[0][7]==2)
# daily usage export: 1 gün (7/15), aralık içi 2 kayıt toplamı
ck("daily export 1 gün", len(drows)==1)
ck("daily tarih", drows[0][0]=="2026-07-15")
ck("daily istek sayısı=2", drows[0][1]==2)
ck("daily total_tokens=40", drows[0][4]==40)
ck("daily cost=0.015", abs(drows[0][5]-0.015)<1e-9)

fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
