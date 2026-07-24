import os
os.environ.update(MYSQL_USER='u',MYSQL_PASSWORD='p',MYSQL_HOST='h',MYSQL_DATABASE='d',MYSQL_PORT='3306')
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from Services import db
from Services.models import UsageLog

eng = create_engine("sqlite:///:memory:")
UsageLog.__table__.create(eng)
db.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)

with db.get_session() as s:
    s.add(UsageLog(sender="90111",model="gpt-4.1-mini",prompt_tokens=50,completion_tokens=50,total_tokens=100,cost=0.01,response_time=1.0,timestamp=datetime.now()))
    s.add(UsageLog(sender="90222",model="gpt-4o",prompt_tokens=100,completion_tokens=100,total_tokens=200,cost=0.02,response_time=2.0,timestamp=datetime.now()))

# get_usd_try_rate dış API — patch'le
import Services.dashboard_service as ds
ds.get_usd_try_rate = lambda: 40.0

d = ds.get_dashboard_data()
res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")

ck("dashboard hatasız döndü (boş değil)", d["recent_activity"] is not None and "business" in d)
ck("2 istek toplam işlendi", len(d["recent_activity"])==2)
ck("charts tam (4 grafik)", set(d["charts"].keys())=={"daily_trend","hourly_activity","model_distribution","top_customers"})
ck("top_customers 2 müşteri", len(d["charts"]["top_customers"]["labels"])==2)
ck("model_distribution 2 model", len(d["charts"]["model_distribution"]["labels"])==2)
# ana özet tuple doğru okundu mu — business/usage/performance dolu olmalı
ck("business özeti üretildi", isinstance(d["business"], dict) and len(d["business"])>0)
ck("usage özeti üretildi", isinstance(d["usage"], dict) and len(d["usage"])>0)
ck("performance özeti üretildi", isinstance(d["performance"], dict) and len(d["performance"])>0)

fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
