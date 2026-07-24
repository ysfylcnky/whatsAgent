import os
os.environ.update(MYSQL_USER='u',MYSQL_PASSWORD='p',MYSQL_HOST='h',MYSQL_DATABASE='d',MYSQL_PORT='3306')
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from Services import db
from Services.models import Conversation, Customer

eng = create_engine("sqlite:///:memory:")
Conversation.__table__.create(eng); Customer.__table__.create(eng)
db.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)

# Test verisi: 3 müşteri, farklı mesaj sayıları/zamanları, biri customers'ta yok
with db.get_session() as s:
    s.add(Customer(phone="90111", ad_soyad="Ali Veli", first_seen=datetime.now(), last_seen=datetime.now()))
    s.add(Customer(phone="90222", ad_soyad="Ayşe Şen", first_seen=datetime.now(), last_seen=datetime.now()))
    # 90333 müşteri tablosunda YOK (ad_soyad None olmalı)
    data = [
        ("90111","gelen","ilk mesaj", datetime(2026,7,1,9,0)),
        ("90111","giden","cevap 1", datetime(2026,7,1,9,5)),
        ("90111","gelen","Ali son mesaj çğü", datetime(2026,7,1,9,10)),
        ("90222","gelen","Ayşe tek mesaj", datetime(2026,7,2,14,0)),
        ("90333","gelen","kayıtsız müşteri mesajı "+"x"*100, datetime(2026,7,3,16,0)),
    ]
    for snd,d,c,t in data:
        s.add(Conversation(sender=snd, direction=d, content=c, timestamp=t))

# --- ESKİ ham SQL (SQLite uyarlaması: SUBSTRING→substr) ---
raw_sql = text("""
    SELECT c.sender, MAX(cu.ad_soyad), COUNT(*), MAX(c.timestamp),
        substr((SELECT c2.content FROM conversations c2 WHERE c2.sender=c.sender
                ORDER BY c2.timestamp DESC, c2.id DESC LIMIT 1), 1, 80)
    FROM conversations c LEFT JOIN customers cu ON cu.phone=c.sender
    GROUP BY c.sender ORDER BY MAX(c.timestamp) DESC LIMIT 50 OFFSET 0
""")
with eng.connect() as conn:
    old_rows = [tuple(r) for r in conn.execute(raw_sql).fetchall()]

# --- YENİ ORM ---
from Services.dashboard_service import get_conversations_list
r = get_conversations_list(page=1, page_size=50)
new_items = r["items"]

res=[]
def ck(n,c): res.append((n,c)); print(f"{'✅' if c else '❌'} {n}")

ck("total=3 farklı müşteri", r["total"]==3)
ck("3 satır döndü", len(new_items)==3)
# Sıralama: en son mesaj zamanı DESC → 90333(7/3), 90222(7/2), 90111(7/1)
ck("sıralama last_time DESC", [i["sender"] for i in new_items]==["90333","90222","90111"])
# msg_count
counts={i["sender"]:i["msg_count"] for i in new_items}
ck("90111 mesaj sayısı=3", counts["90111"]==3)
ck("90222 mesaj sayısı=1", counts["90222"]==1)
# ad_soyad JOIN
names={i["sender"]:i["ad_soyad"] for i in new_items}
ck("90111 adı JOIN'den", names["90111"]=="Ali Veli")
ck("90333 adı None (customers'ta yok)", names["90333"] is None)
# last_content: en son mesajın ilk 80 karakteri
lc={i["sender"]:i["last_content"] for i in new_items}
ck("90111 son mesaj doğru", lc["90111"]=="Ali son mesaj çğü")
ck("90333 son mesaj 80 karaktere kesildi", len(lc["90333"])==80)
# last_time biçimi
ck("last_time biçimi Y-m-d H:M", new_items[2]["last_time"]=="2026-07-01 09:10")
# ESKİ vs YENİ birebir: sender, count, kesilmiş içerik
old_map={row[0]:(row[2], (row[4] or "")[:80]) for row in old_rows}
match=all(old_map[i["sender"]][0]==i["msg_count"] and old_map[i["sender"]][1]==i["last_content"] for i in new_items)
ck("ESKİ ham SQL ile YENİ ORM birebir eşleşiyor", match)

fail=[n for n,c in res if not c]
print(f"\n{len(res)-len(fail)}/{len(res)} geçti")
import sys; sys.exit(1 if fail else 0)
