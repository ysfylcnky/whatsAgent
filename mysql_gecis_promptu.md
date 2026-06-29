# Görev: SQLite → MySQL geçişi + dashboard için eksik backend verilerinin tamamlanması

## Bağlam
Bu proje, NilNur Moda butiği için **FastAPI** tabanlı bir WhatsApp yapay zeka satış asistanı. Her OpenAI çağrısının token/maliyet/süre bilgisi şu an **SQLite** (`usage_logs.db`) ile kaydediliyor ve `/admin/dashboard` endpoint'i bu veriyi dashboard'a (Chart.js) besliyor.

İki sorunu çözeceksin:
1. Veri kaydını **SQLite'tan MySQL'e** taşı.
2. Frontend'in (`static/js/dashboard.js`) beklediği ama backend'in **döndürmediği** grafik verilerini üret.

Çalışmaya başlamadan önce şu dosyaları oku ve mevcut yapıyı anla:
`Services/usage_logger.py`, `Services/dashboard_service.py`, `Services/currency_service.py`, `seed_demo_data.py`, `config.py`, `main.py`, `static/js/dashboard.js`.

---

## Bölüm 1 — SQLite yerine MySQL

**Kütüphane:** `mysql-connector-python` kullan (resmi sürücü). ORM kullanma; mevcut raw SQL stilini koru.

### Yapılacaklar
- `requirements.txt`'e `mysql-connector-python` ekle. SQLite zaten standart kütüphane, kaldıracak bir paket yok.
- **Bağlantı bilgilerini `.env`'den oku**, `config.py`'de değişkenlere bağla:
  ```
  MYSQL_HOST, MYSQL_PORT (varsayılan 3306), MYSQL_USER,
  MYSQL_PASSWORD, MYSQL_DATABASE
  ```
  `.env`'i commit etme; `.gitignore`'da `.env` zaten var. `.env`'e örnek satırları ben dolduracağım, sen sadece `config.py`'de bu değişkenleri tanımla.
- `Services/usage_logger.py` dosyasını MySQL'e göre baştan yaz:
  - Tek bir yerden yönetilen **bağlantı havuzu** (`mysql.connector.pooling.MySQLConnectionPool`) kur; her fonksiyon havuzdan bağlantı alıp iş bitince geri bıraksın. Her çağrıda yeni `connect()` açma.
  - `initialize_database()`: veritabanı/tablo yoksa oluştursun. MySQL şeması:
    ```sql
    CREATE TABLE IF NOT EXISTS usage_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        timestamp DATETIME NOT NULL,
        sender VARCHAR(32) NOT NULL,
        model VARCHAR(64) NOT NULL,
        prompt_tokens INT NOT NULL,
        completion_tokens INT NOT NULL,
        total_tokens INT NOT NULL,
        cost DOUBLE NOT NULL,
        response_time DOUBLE NOT NULL,
        INDEX idx_timestamp (timestamp),
        INDEX idx_sender (sender)
    );
    ```
    Not: `timestamp` artık metin değil gerçek `DATETIME` olsun (tarih/saat bazlı grafikleri kolaylaştırır). Yazarken `datetime` nesnesi gönder.
  - `log_usage(...)`, `get_total_requests()`, `get_total_tokens()`, `get_total_cost()`, `get_average_response_time()`, `get_usage_summary()` fonksiyonlarını MySQL parametre stiliyle (`%s` placeholder) yeniden yaz. Dışarıya verdikleri imza ve dönüş tipleri **aynı kalsın** ki çağıran kod değişmesin.
- `Services/dashboard_service.py` artık MySQL'den okusun (aşağıdaki Bölüm 2 ile birlikte güncellenecek). SQLite `import sqlite3` ve `sqlite3.connect(DB_NAME)` kullanımlarını kaldır; havuzdan bağlantı al.
- `seed_demo_data.py`'yi de MySQL'e yazacak şekilde güncelle (aynı havuzu/aynı bağlantı ayarlarını kullansın). Mevcut SQLite verisini **taşıma**; sıfırdan başlıyoruz, seed yeniden dolduracak.
- Projede `usage_logs.db` ve SQLite'a dair başka referans kalmasın.

### Hata yönetimi
- MySQL'e bağlanılamazsa uygulama **komple çökmesin**: webhook akışı (WhatsApp mesaj yanıtlama) loglama hatasından etkilenmemeli. `log_usage` içinde hata olursa yakala, logla, ama yanıt akışını kesme.
- `get_dashboard_data()` veritabanı boşsa/erişilemezse anlamlı boş yapı (sıfırlar, boş diziler) dönsün; frontend `undefined` ile patlamasın.

---

## Bölüm 2 — Frontend'in beklediği eksik veriler

`static/js/dashboard.js` şu alanları okuyor ama `get_dashboard_data()` bunları **üretmiyor**: `data.charts.daily_trend`, `data.charts.hourly_activity`, `data.charts.model_distribution`, `data.charts.top_customers`, `data.recent_activity`. Bunları backend'de hesaplayıp döndür.

> Önce `static/js/dashboard.js` içindeki `render`, `renderTrend`, `renderHourly`, `renderModel`, `renderTopCustomers`, `renderTimeline` fonksiyonlarını oku ve **alan adlarını birebir doğrula**. Aşağıdaki kontrat bu dosyadan çıkarıldı; uyuşmazlık olursa JS'i esas al.

### `/admin/dashboard` dönüş kontratı (hedef)
```json
{
  "business":    { "unique_customers": 0, "total_requests": 0, "estimated_saved_hours": 0,
                   "estimated_employee_cost": 0, "ai_cost_try": 0, "estimated_savings": 0 },
  "usage":       { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                   "total_cost_usd": 0, "total_cost_try": 0, "usd_try_rate": 0 },
  "performance": { "average_response_time": 0 },

  "charts": {
    "daily_trend": {
      "labels":    ["2026-06-16", "..."],
      "requests":  [12, "..."],
      "tokens":    [34000, "..."],
      "cost":      [0.0123, "..."],
      "customers": [5, "..."]
    },
    "hourly_activity": {
      "labels":   ["00:00","01:00", "...", "23:00"],
      "requests": [0, 0, "...", 0]
    },
    "model_distribution": {
      "labels":   ["gpt-4.1-mini", "gpt-4o-mini-transcribe"],
      "requests": [120, 18]
    },
    "top_customers": {
      "labels":   ["905321112233", "..."],
      "requests": [42, "..."]
    }
  },

  "recent_activity": [
    { "sender": "905321112233", "model": "gpt-4.1-mini",
      "total_tokens": 540, "response_time": 1.83, "timestamp": "2026-06-29 14:23:01" }
  ]
}
```

### Hesaplama kuralları (SQL ile yap, Python'da döngüyle değil)
- **daily_trend** — son **14 günü** kapsa. Gün bazında grupla:
  `DATE(timestamp)` → `labels`; `COUNT(*)` → `requests`; `SUM(total_tokens)` → `tokens`;
  `SUM(cost)` → `cost`; `COUNT(DISTINCT sender)` → `customers`.
  Veri olmayan günler **0** ile doldurulsun ki dizi 14 elemanlı ve tarih sırası kesintisiz olsun (eksik günleri Python tarafında tamamla).
- **hourly_activity** — 0–23 arası **24 saatin tamamı** olsun. `HOUR(timestamp)` → grupla, `COUNT(*)` → `requests`. Hiç istek olmayan saat 0. (İstersen son N gün veya tüm zaman; tercihen tüm kayıtlar üzerinden saat dağılımı.)
- **model_distribution** — `model` alanına göre `GROUP BY`, `COUNT(*)` ile sırala (çok → az).
- **top_customers** — `sender`'a göre `GROUP BY`, `COUNT(*) DESC`, `LIMIT 8`.
- **recent_activity** — `ORDER BY timestamp DESC LIMIT 10`; alanlar: `sender, model, total_tokens, response_time, timestamp`. `timestamp`'i `"YYYY-MM-DD HH:MM:SS"` string olarak ver.
- **Mevcut `business` / `usage` / `performance` mantığını koru.** `dashboard_service.py` içindeki `get_business_summary`, `get_usage_summary`, `get_performance_summary` ve USD/TRY kuru (`currency_service.get_usd_try_rate`) hesapları aynı çalışmaya devam etsin; sadece üstüne `charts` ve `recent_activity` ekle.

---

## Kısıtlar
- Çalışan webhook/WhatsApp/OpenAI akışını **bozma**; sadece veri katmanını ve dashboard verisini değiştiriyorsun.
- Mevcut kod stiline uy: Türkçe yorumlar, raw SQL, fonksiyon imzalarını koru.
- `.env` ve gizli bilgileri commit etme.
- Gereksiz bağımlılık ekleme; sadece `mysql-connector-python`.

## Kabul kriterleri
1. `pip install -r requirements.txt` sonrası `python seed_demo_data.py` çalışıp MySQL'e 14 günlük demo veri yazıyor.
2. Uygulama ayağa kalkıyor; `/admin/dashboard` yukarıdaki kontratın **tüm** alanlarını dolu döndürüyor.
3. `/dashboard` açıldığında trend grafiği, saatlik bar, donut, model dağılımı, top customers ve aktivite zaman tüneli **boş/hatalı değil**, dolu görünüyor (JS konsolunda `undefined` hatası yok).
4. MySQL kapalıyken uygulama çökmüyor; webhook yanıt vermeye devam ediyor, dashboard anlamlı boş yapı dönüyor.

## Teslimden önce
Yaptığın değişikliklerin özetini ve `.env`'e eklemem gereken MySQL değişkenlerinin listesini bana ver. Test ederken kullandığın komutları da yaz.
