"""
Dashboard'u dolu göstermek için gerçekçi ÖRNEK veri üretir (MySQL).
Çalıştır:   python seed_demo_data.py
Temizle:    python seed_demo_data.py --clear
"""

import sys

# Windows konsolu (cp1254) emoji içeren print'lerde çökmesin diye UTF-8'e geç
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import random
from datetime import datetime, timedelta

from Services.usage_logger import initialize_database, get_connection

INPUT_PRICE = 0.40 / 1_000_000   # USD / token
OUTPUT_PRICE = 1.60 / 1_000_000

SENDERS = [
    "905321112233", "905337778899", "905445556677",
    "905552223344", "905061114455", "905369998877",
    "905541239988", "905307654321", "905398887766",
    "905421119900",
]

# Bazı müşteriler çok daha aktif (top customers grafiği için)
SENDER_WEIGHTS = [9, 7, 6, 5, 4, 3, 3, 2, 2, 1]

MODELS = ["gpt-4.1-mini"] * 6 + ["gpt-4o-mini-transcribe"] * 1


def clear():
    initialize_database()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM usage_logs")
    conn.commit()
    cur.close()
    conn.close()
    print("Tum demo veriler silindi.")


def seed():
    initialize_database()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM usage_logs")

    rows = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for day_offset in range(13, -1, -1):
        day = today - timedelta(days=day_offset)

        # Yukari dogru trend + hafta sonu dususu
        base = 14 + (13 - day_offset) * 1.6
        if day.weekday() >= 5:
            base *= 0.55
        daily_count = max(3, int(random.gauss(base, 4)))

        for _ in range(daily_count):
            # Mesai saatlerinde yogunlasan saat dagilimi
            hour = random.choices(
                population=list(range(24)),
                weights=[1, 1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8,
                         9, 10, 9, 7, 6, 6, 8, 9, 7, 5, 3, 2],
                k=1,
            )[0]
            ts = day + timedelta(
                hours=hour,
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59),
            )

            sender = random.choices(SENDERS, weights=SENDER_WEIGHTS, k=1)[0]
            model = random.choice(MODELS)

            prompt = random.randint(220, 1600)
            completion = random.randint(60, 620)
            total = prompt + completion
            cost = round(prompt * INPUT_PRICE + completion * OUTPUT_PRICE, 6)
            rt = round(random.uniform(0.7, 4.6), 3)

            rows.append((
                ts,
                sender, model, prompt, completion, total, cost, rt,
            ))

    # timestamp artik gercek DATETIME; datetime nesnesine gore sirala
    rows.sort(key=lambda r: r[0])

    cur.executemany(
        """INSERT INTO usage_logs
           (timestamp, sender, model, prompt_tokens, completion_tokens,
            total_tokens, cost, response_time)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        rows,
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"{len(rows)} demo kayit eklendi ({len(SENDERS)} musteri, 14 gun).")


if __name__ == "__main__":
    if "--clear" in sys.argv:
        clear()
    else:
        seed()
