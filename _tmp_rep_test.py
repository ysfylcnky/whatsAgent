import os
os.environ.update(MYSQL_USER='u',MYSQL_PASSWORD='p',MYSQL_HOST='h',MYSQL_DATABASE='d',MYSQL_PORT='3306')
from datetime import datetime
from sqlalchemy import create_engine, text, Integer
from sqlalchemy.orm import sessionmaker
from Services import db
from Services.models import UsageLog, Order, Conversation
Order.__table__.c.is_update.type = Integer()

eng = create_engine("sqlite:///:memory:")
UsageLog.__table__.create(eng); Order.__table__.create(eng); Conversation.__table__.create(eng)
db.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)

# Aralık: 2026-07-01 .. 2026-07-31
inr = datetime(2026,7,15,10,0)   # aralık içi
out = datetime(2026,6,20,10,0)   # aralık dışı
with db.get_session() as s:
    # usage_logs
    s.add(UsageLog(sender="90111",model="m",prompt_tokens=10,completion_tokens=10,total_tokens=20,cost=0.01,response_time=1.0,timestamp=inr))
    s.add(UsageLog(sender="90222",model="m",prompt_tokens=20,completion_tokens=20,total_tokens=40,cost=0.02,response_time=2.0,timestamp=inr))
    s.add(UsageLog(sender="90111",model="m",prompt_tokens=5,completion_tokens=5,total_tokens=10,cost=0.005,response_time=1.5,timestamp=out))  # dışı
    # orders: 2 gerçek (Havale, "  " boş→Belirtilmemiş), 1 güncelleme
    def o(upd,adet,ode,t): s.add(Order(customer_phone="90111",ad_soyad="x",telefon="x",teslimat_adresi="a",urun="U",renk="K",beden="M",adet=adet,odeme_sekli=ode,is_update=upd,timestamp=t))
    o(0,2,"Havale",inr); o(0,3,"   ",inr); o(1,1,"Havale",inr); o(0,5,"Havale",out)  # sonuncusu aralık dışı
    # conversations: 2 gelen, 1 giden, aralık içi; 2 farklı sender
    s.add(Conversation(sender="90111",direction="gelen",content="a",timestamp=inr))
    s.add(Conversation(sender="90222",direction="gelen",content="b",timestamp=inr))
    s.add(Conversation(sender="90111",direction="giden",content="c",timestamp=inr))
    s.add(Conversation(sender="90333",direction="gelen",content="d",timestamp=out))  # dışı

import Services.dashboard_service as ds
ds.get_usd_try_rate = lambda: 40.0
r = ds.get_report_summary("2026-07-01","2026-07-31")

res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")
# AI (sadece aralık içi 2 kayıt)
ck("AI istek=2 (aralık içi)", r["ai"]["requests"]==2)
ck("AI maliyet=0.03", abs(r["ai"]["cost_usd"]-0.03)<1e-9)
ck("AI cost_try hesaplandı", r["ai"]["cost_try"]==round(0.03*40,2))
# Orders (aralık içi: 2 gerçek + 1 güncelleme)
ck("sipariş sayısı=2 (gerçek)", r["orders"]["count"]==2)
ck("güncelleme sayısı=1", r["orders"]["update_count"]==1)
ck("toplam adet=5 (2+3, güncelleme hariç)", r["orders"]["total_quantity"]==5)
# Ödeme dağılımı: Havale(1), Belirtilmemiş(1) — boş odeme_sekli
byp={p["odeme_sekli"]:p["count"] for p in r["orders"]["by_payment"]}
ck("ödeme Havale=1", byp.get("Havale")==1)
ck("ödeme boş→Belirtilmemiş=1", byp.get("Belirtilmemiş")==1)
# Messages (aralık içi: 2 gelen, 1 giden, 2 farklı sender)
ck("gelen mesaj=2", r["messages"]["incoming"]==2)
ck("giden mesaj=1", r["messages"]["outgoing"]==1)
ck("farklı müşteri=2", r["messages"]["unique_customers"]==2)

# ESKİ ham SQL ile orders count karşılaştır
with eng.connect() as conn:
    old_o = conn.execute(text("SELECT COUNT(CASE WHEN is_update=0 THEN 1 END), SUM(CASE WHEN is_update=0 THEN adet END) FROM orders WHERE timestamp>='2026-07-01' AND timestamp<'2026-08-01'")).fetchone()
ck("orders ESKİ ile eşleşiyor", r["orders"]["count"]==old_o[0] and r["orders"]["total_quantity"]==int(old_o[1] or 0))

fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
