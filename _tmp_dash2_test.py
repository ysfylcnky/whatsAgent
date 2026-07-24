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
    def add(snd,mdl,tok,cost,rt,t): s.add(UsageLog(sender=snd,model=mdl,prompt_tokens=tok//2,completion_tokens=tok//2,total_tokens=tok,cost=cost,response_time=rt,timestamp=t))
    # bugün 3 istek (2 müşteri), dün 2 istek (1 müşteri), 5 gün önce 1
    add("90111","gpt-4.1-mini",100,0.01,1.0, today.replace(hour=9))
    add("90111","gpt-4.1-mini",120,0.012,1.2, today.replace(hour=9,minute=30))
    add("90222","gpt-4o",200,0.02,0.8, today.replace(hour=14))
    add("90111","gpt-4.1-mini",90,0.009,1.1, (today-timedelta(days=1)).replace(hour=10))
    add("90111","gpt-4.1-mini",110,0.011,1.3, (today-timedelta(days=1)).replace(hour=10,minute=5))
    add("90333","gpt-4o",300,0.03,2.0, (today-timedelta(days=5)).replace(hour=16))

res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")

from Services.dashboard_service import _get_daily_trend, _get_hourly_activity, _get_model_distribution

# daily_trend
dt = _get_daily_trend()
ck("daily_trend 14 gün", len(dt["labels"])==14 and len(dt["requests"])==14)
ck("daily_trend bugün 3 istek", dt["requests"][13]==3)
ck("daily_trend dün 2 istek", dt["requests"][12]==2)
ck("daily_trend bugün 2 müşteri", dt["customers"][13]==2)
ck("daily_trend 5 gün önce 1 istek", dt["requests"][8]==1)
ck("daily_trend eksik günler 0", dt["requests"][0]==0)
ck("daily_trend token toplamı bugün", dt["tokens"][13]==420)

# hourly_activity
ha = _get_hourly_activity()
ck("hourly 24 saat", len(ha["requests"])==24)
ck("hourly saat 9'da 3 istek (bugün2+dün? hayır dün saat10)", ha["requests"][9]==2)  # bugün 9:00 ve 9:30 = 2
ck("hourly saat 10'da 2 (dün)", ha["requests"][10]==2)
ck("hourly saat 14'te 1", ha["requests"][14]==1)

# model_distribution
md = _get_model_distribution()
# gpt-4.1-mini: 4 istek, gpt-4o: 2 istek
ck("model_dist sıralama (çok->az)", md["labels"][0]=="gpt-4.1-mini" and md["requests"]==[4,2])

# ESKİ ham SQL ile karşılaştır (hourly)
with eng.connect() as conn:
    old_hourly = {int(h):c for h,c in conn.execute(text(
        "SELECT CAST(strftime('%H',timestamp) AS INT), COUNT(*) FROM usage_logs GROUP BY 1")).fetchall()}
ck("hourly ESKİ ile eşleşiyor", all(ha["requests"][h]==old_hourly.get(h,0) for h in range(24)))

fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
