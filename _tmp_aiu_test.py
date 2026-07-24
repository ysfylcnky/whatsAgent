import os
os.environ.update(MYSQL_USER='u',MYSQL_PASSWORD='p',MYSQL_HOST='h',MYSQL_DATABASE='d',MYSQL_PORT='3306')
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from Services import db
from Services.models import UsageLog

eng = create_engine("sqlite:///:memory:")
UsageLog.__table__.create(eng)
db.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)

today = datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
with db.get_session() as s:
    def add(snd,mdl,pt,ct,cost,rt,t): s.add(UsageLog(sender=snd,model=mdl,prompt_tokens=pt,completion_tokens=ct,total_tokens=pt+ct,cost=cost,response_time=rt,timestamp=t))
    # gpt-4o pahalı, gpt-4.1-mini ucuz
    add("90111","gpt-4.1-mini",50,50,0.001,1.0, today.replace(hour=9))
    add("90111","gpt-4.1-mini",60,40,0.0012,1.1, today.replace(hour=10))
    add("90222","gpt-4o",100,100,0.05,2.0, today.replace(hour=11))
    add("90222","gpt-4o",120,80,0.04,1.8, (today-timedelta(days=2)).replace(hour=12))
    add("90333","gpt-4.1-mini",30,30,0.0008,0.9, (today-timedelta(days=1)).replace(hour=13))

import Services.dashboard_service as ds
ds.get_usd_try_rate = lambda: 40.0
d = ds.get_ai_usage_detail()

res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")

# summary
ck("toplam istek 5", d["summary"]["total_requests"]==5)
ck("toplam maliyet doğru", abs(d["summary"]["total_cost_usd"] - (0.001+0.0012+0.05+0.04+0.0008)) < 1e-9)
ck("TRY maliyet hesaplandı", d["summary"]["total_cost_try"] is not None)
# by_model: maliyete göre azalan → gpt-4o (0.09) önce, gpt-4.1-mini (0.003) sonra
ck("model sıralaması maliyete göre", [m["model"] for m in d["by_model"]]==["gpt-4o","gpt-4.1-mini"])
ck("gpt-4o 2 istek", d["by_model"][0]["requests"]==2)
ck("gpt-4.1-mini 3 istek", d["by_model"][1]["requests"]==3)
# daily: AI_USAGE_TREND_DAYS gün
ck("daily trend gün sayısı", len(d["daily"]["labels"])==ds.AI_USAGE_TREND_DAYS)
ck("daily bugün 3 istek", d["daily"]["requests"][-1]==3)
ck("daily dün 1 istek", d["daily"]["requests"][-2]==1)
ck("daily 2 gün önce 1 istek", d["daily"]["requests"][-3]==1)
# top_customers_by_cost: 90222 (0.09) en pahalı
ck("top müşteri maliyete göre 90222", d["top_customers_by_cost"][0]["sender"]=="90222")
ck("top müşteri 3 kayıt", len(d["top_customers_by_cost"])==3)

# ESKİ ham SQL ile by_model karşılaştır
with eng.connect() as conn:
    old=[(r[0],r[1]) for r in conn.execute(text("SELECT model, COUNT(*) FROM usage_logs GROUP BY model ORDER BY SUM(cost) DESC")).fetchall()]
ck("by_model ESKİ ile eşleşiyor", [(m["model"],m["requests"]) for m in d["by_model"]]==old)

fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
