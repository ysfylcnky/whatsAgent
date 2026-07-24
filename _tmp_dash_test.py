import os
os.environ.update(MYSQL_USER='u',MYSQL_PASSWORD='p',MYSQL_HOST='h',MYSQL_DATABASE='d',MYSQL_PORT='3306')
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from Services import db
from Services.models import UsageLog

eng = create_engine("sqlite:///:memory:")
UsageLog.__table__.create(eng)
db.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)

# Test verisi: 3 müşteri farklı istek sayılarıyla, 12 kayıt (recent 10 testi için)
with db.get_session() as s:
    def add(snd, mdl, tok, rt, t): s.add(UsageLog(sender=snd, model=mdl, prompt_tokens=1, completion_tokens=1, total_tokens=tok, cost=0.001, response_time=rt, timestamp=t))
    # 90111: 5 istek, 90222: 3, 90333: 4
    for i in range(5): add("90111","gpt-4.1-mini",100+i,1.2, datetime(2026,7,1,10,i))
    for i in range(3): add("90222","gpt-4.1-mini",200+i,0.9, datetime(2026,7,2,11,i))
    for i in range(4): add("90333","gpt-4.1-mini",300+i,1.5, datetime(2026,7,3,12,i))

# --- ESKİ ham SQL ---
with eng.connect() as conn:
    old_top = [tuple(r) for r in conn.execute(text(
        "SELECT sender, COUNT(*) FROM usage_logs GROUP BY sender ORDER BY COUNT(*) DESC LIMIT 8")).fetchall()]
    old_recent = [tuple(r) for r in conn.execute(text(
        "SELECT sender, model, total_tokens, response_time, timestamp FROM usage_logs ORDER BY timestamp DESC LIMIT 10")).fetchall()]

# --- YENİ ORM ---
from Services.dashboard_service import _get_top_customers, _get_recent_activity
top = _get_top_customers()
recent = _get_recent_activity()

res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")

# top_customers: 90111(5), 90333(4), 90222(3) sırasıyla
ck("top_customers sıralaması (istek sayısı DESC)", top["labels"]==["90111","90333","90222"])
ck("top_customers sayıları", top["requests"]==[5,4,3])
ck("top_customers ESKİ ile eşleşiyor", list(zip(top["labels"],top["requests"]))==[(r[0],r[1]) for r in old_top])
# recent_activity: son 10, timestamp DESC. En yeni: 90333 12:03
ck("recent 10 kayıt", len(recent)==10)
ck("recent en yeni önce", recent[0]["sender"]=="90333")
ck("recent timestamp biçimi", recent[0]["timestamp"]=="2026-07-03 12:03:00")
ck("recent alanları tam", set(recent[0].keys())=={"sender","model","total_tokens","response_time","timestamp"})
# ESKİ recent ile karşılaştır (ilk 10 sender sırası)
ck("recent ESKİ ile sender sırası eşleşiyor", [r["sender"] for r in recent]==[row[0] for row in old_recent])
fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
