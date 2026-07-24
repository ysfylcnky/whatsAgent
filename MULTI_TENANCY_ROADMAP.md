# whatsAgent — Multi-Tenant SaaS Yol Haritası

Bu belge, projeyi tek mağazalık yapıdan (single-tenant) çok müşterili gerçek
bir SaaS'a (multi-tenant) dönüştürmenin aşamalı planıdır. Kod yazmadan önce
referans olması içindir. Her faz bağımsız, test edilebilir ve geri
alınabilir olacak şekilde tasarlanmıştır.

---

## 🏁 MILESTONE 1 — ORM Okuma Tarafı Tamamlandı (2026-07-22)

Bu nokta bilinçli bir duraktır: **panelin tüm OKUMA tarafı ham SQL'den ORM'e
taşındı**, yazma yollarına henüz dokunulmadı. Temiz ve güvenli bir kesme noktası.

**Bu milestone'a kadar tamamlananlar (bugüne dek yapılan tüm işle birlikte):**
- ✅ Stateless mimari (Redis) — yatay ölçekleme mümkün
- ✅ JWT auth (bcrypt, httpOnly çerez) — Basic Auth kaldırıldı
- ✅ Responsive panel — mobil hamburger + drawer
- ✅ Production Docker'a taşındı (app + mysql + redis), reboot testi geçti
- ✅ Faz 0.1–0.12: `Services/db.py` + `Services/models.py` (ORM zemini) ve
  `Services/dashboard_service.py` **tamamen ORM** (5 sayfa + CSV export'lar).
  Her adım SQLite ile eski/yeni birebir karşılaştırılarak doğrulandı.

**Bu noktada durum:** Okuma tarafı ORM, yazma tarafı hâlâ ham SQL. Sistem
tam çalışır ve stabil. Mumi tek tenant olarak production'da.

**Geri dönüş işareti (öneri):** bu noktaya git tag'i koy:
```
git tag -a v0.3-orm-reads -m "Milestone 1: ORM okuma tarafi tamamlandi"
git push origin v0.3-orm-reads
```

**Sıradaki (Milestone 2'ye giden) — YAZMA yolları, en kritik grup:**
`usage_logger.log_usage`, `order_service.save_order`, customers upsert,
`settings_service`. Bunlar webhook akışının içinde gerçek veri yazar; her biri
SQLite + gerçek WhatsApp siparişiyle iki kez test edilecek. Bir hata burada
görüntüyü değil kaydedilen veriyi etkiler — ekstra dikkat.

---

**Hedef senaryo:** `mumifashion.com` tanıtım sitesinden gelen müşteri
"Giriş yap" → e-posta + şifre → yalnız kendi mağazasının verilerini gördüğü
dashboard. 50+ müşteri aynı sistemi kullanır; hiçbiri diğerinin verisini
göremez.

---

## Bugünkü durum (başlangıç noktası)

| Konu | Mevcut | Hedef |
|---|---|---|
| Veri | 5 tablo, hepsi tek mağazaya ait | Her tabloda `tenant_id`, izole |
| Ayarlar | Tek `.env` (ikas, WhatsApp, IBAN…) | Müşteri başına DB'de |
| WhatsApp | Tek numara | 50 numara → doğru tenant'a yönlenir |
| Giriş | Tek kullanıcı, JWT ✅ | E-posta/şifre, çok kullanıcı, tenant'a bağlı |
| Kayıt | Yok (elle kurulum) | Self-service onboarding |
| DB erişimi | Ham SQL (elle) | ORM (merkezi, güvenli filtreleme) |

**Tamamlanmış ön koşullar (bugün yapıldı):** Stateless mimari (Redis) ✅,
JWT altyapısı ✅, Docker ✅. Bunlar multi-tenant'ın zeminidir.

---

## Faz 0 — ORM'e geçiş (ÖN KOŞUL)

> **İlerleme (2026-07-21):**
> - ✅ 0.1 SQLAlchemy zemini (`Services/db.py` — engine, session, Base).
> - ✅ 0.2 ORM modelleri (`Services/models.py` — 5 tablo, şemayla birebir).
> - ✅ 0.3 Şema doğrulaması (`debug_orm_schema.py`, canlıda 23/23).
> - ✅ 0.4 Pilot: `conversation_logger` (conversations yazma) ORM'e taşındı,
>   canlıda doğrulandı (28/28 + gerçek mesaj testi, hata yok).
> - ✅ 0.5 `get_conversation_detail` (conversations okuma) ORM'e taşındı;
>   SQLite izole testi 9/9 (çıktı sözleşmesi + izolasyon korundu).
> - ✅ 0.6 `get_conversations_list` (JOIN + GROUP BY + correlated subquery)
>   ORM'e; eski ham SQL ile yeni ORM aynı veride birebir eşleşti (11/11).
> - ✅ 0.7 dashboard `_get_top_customers` + `_get_recent_activity` (usage_logs)
>   ORM'e; bağımsız oturum, eski/yeni birebir (8/8).
> - ✅ 0.8 `get_dashboard_data` tamamen ORM'e (daily_trend, hourly, model_dist
>   + ana özet); cursor kalktı. func.date/extract dialect-bağımsız. 13/13 + uçtan
>   uca 8/8. Dashboard ANA SAYFASI artık tamamen ORM.
> - ✅ 0.9 `get_customers_list` (customers LEFT JOIN orders + CASE) ve
>   `get_customer_detail` (customers + orders) ORM'e; 14/14, eski/yeni birebir.
>   Customers SAYFASI artık ORM.
> - ✅ 0.10 `get_ai_usage_detail` (4 usage_logs sorgusu: özet, model kırılımı,
>   günlük trend, maliyet-top müşteri) ORM'e; 13/13. AI Usage SAYFASI artık ORM.
> - ✅ 0.11 `get_report_summary` (3 tablo: usage_logs+orders+conversations,
>   CASE/COALESCE/NULLIF/TRIM, tarih aralıklı) ORM'e; 12/12, eski/yeni birebir.
> - ✅ 0.12 CSV export'lar (`get_orders_export_rows`, `get_daily_usage_export_rows`)
>   ORM'e; 11/11. **`dashboard_service.py` ARTIK TAMAMEN ORM** — get_connection
>   import'u kaldırıldı, cursor kalmadı. Panelin tüm OKUMA tarafı bitti.
> - ⏳ Sırada — YAZMA yolları (en kritik, tenant izolasyonunun kalbi):
>   `usage_logger` (log_usage), `order_service` (save_order), customers upsert.
>   Sonra `settings_service`. Bunlar webhook akışından çağrılır; SQLite +
>   gerçek WhatsApp mesajıyla test edilecek.

**Neden ilk:** Kod şu an ~40 yerde ham SQL yazıyor (`WHERE sender = %s`).
Multi-tenant'ta her sorguya elle `AND tenant_id = %s` eklemek gerekir; tek bir
unutulan sorgu = bir müşterinin başka müşterinin verisini görmesi = veri
sızıntısı + KVKK ihlali. ORM (SQLAlchemy/SQLModel) ile tenant filtresi **tek
merkezden, otomatik** uygulanır (global filter / session event). Bu, tüm
projedeki en kritik güvenlik kararıdır.

**Kapsam:** `Services/` içindeki DB erişen fonksiyonları ORM modellerine taşı.
İş mantığı ve prompt yapısı değişmez; yalnız veri katmanı.

**Risk:** Orta — çok dosyaya dokunur ama davranış aynı kalır. Faz faz, tablo
tablo yapılabilir (önce `conversations`, sonra `orders`…). Her tablo geçişi
`debug_*.py` ile doğrulanır.

**Geri dönüş:** Her tablo ayrı commit; ham SQL sürümüne dönülebilir.

**Büyüklük:** Büyük (en büyük tekil faz). Ama tek seferde değil, tabloya
bölünerek yapılır.

---

## Faz 1 — Tenant veri modeli

**Ne:** İki yeni tablo:
- `tenants` — her müşteri mağazası (id, ad, durum, oluşturulma).
- `users` — panel kullanıcıları (id, tenant_id, e-posta, parola hash, rol).

Ve mevcut 5 tabloya (`conversations`, `customers`, `orders`, `usage_logs`,
`settings`) `tenant_id` sütunu + index.

**Migration stratejisi:** Mevcut tüm veriler "Mumi" adında ilk tenant'a
atanır (`tenant_id = 1`). Böylece bugünkü veri kaybolmaz, tek müşteri olarak
sisteme dahil olur.

**Risk:** Orta — şema değişikliği. Ama additive (sütun ekleme), mevcut veriyi
bozmaz. Migration öncesi tam yedek (backup_mysql.sh zaten var).

**Geri dönüş:** Sütunlar `NULL` kabul ederse eski kod çalışmaya devam eder;
kademeli geçiş mümkün.

**Büyüklük:** Orta.

---

## Faz 2 — E-posta/şifre kimlik doğrulama

**Ne:** Bugünkü JWT altyapısının üstüne inşa:
- Kayıt (`/register`) ve giriş (`/login`) e-posta + şifre ile.
- Parola bcrypt (auth_service.py zaten hazır).
- JWT içine `tenant_id` + `user_id` claim'leri eklenir.
- Parola sıfırlama, e-posta doğrulama (e-posta servisi gerekir: SES/Resend).

**Neden kolay parça:** Token üretimi, doğrulama, çerez, login/logout **zaten
var**. Eklenen tek şey: kullanıcıyı `.env` yerine `users` tablosundan doğrulamak
ve token'a tenant bilgisi koymak.

**Risk:** Düşük-orta. İzole; mevcut auth testleri (debug_auth.py) genişletilir.

**Büyüklük:** Orta.

---

## Faz 3 — Tenant'a özel ayarlar

**Ne:** `.env`'deki müşteriye özel değerler (IKAS_CLIENT_ID, IKAS_CLIENT_SECRET,
WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN, STORE_IBAN, STORE_NOTIFY_PHONE)
DB'ye taşınır — her tenant kendi değerlerini tutar.

**Kolaylaştıran:** `settings` tablosu ve `get_setting()` deseni **zaten var**.
Bunu tenant_id ile genişletmek yeterli. Sistem geneli sırlar (OPENAI_API_KEY,
JWT_SECRET) `.env`'de kalır.

**Güvenlik:** Müşteri API anahtarları DB'de şifreli saklanmalı (at-rest
encryption), düz metin değil.

**Risk:** Orta. `config.py`'deki global okumalar tenant-context'e çevrilir.

**Büyüklük:** Orta.

---

## Faz 4 — WhatsApp webhook yönlendirme

**Ne:** Gelen her webhook'ta `metadata.phone_number_id` var (bugün log'da
görülüyor). Bu değerden hangi tenant olduğu bulunur, o tenant'ın ayarları
yüklenir, mesaj o bağlamda işlenir.

**Kritik nokta:** Bu, request flow'un kalbidir. `phone_number_id → tenant`
eşlemesi hızlı olmalı (Redis cache). Eşleşmeyen numara güvenli reddedilir.

**Risk:** Yüksek — ana akışı değiştirir. Kapsamlı test şart (her tenant için
izole webhook simülasyonu). Redis + session_store zaten tenant-hazır yapılabilir
(oturum anahtarına tenant_id eklenir).

**Büyüklük:** Orta-büyük.

---

## Faz 5 — Veri izolasyonu enforcement

**Ne:** ORM seviyesinde (Faz 0 sayesinde) her sorguya otomatik
`WHERE tenant_id = <aktif_tenant>` uygulanır. Panel API'leri, dashboard
sorguları, raporlar — hepsi yalnız aktif tenant'ın verisini döndürür.

**Doğrulama:** İki test tenant'ı oluştur, birinin token'ıyla diğerinin
verisine erişilemediğini otomatik testle kanıtla. Bu fazın çıktısı bir
**güvenlik testidir**, atlanamaz.

**Risk:** Yüksek (güvenlik). Ama Faz 0 doğru yapıldıysa mekanik.

**Büyüklük:** Orta.

---

## Faz 6 — Self-service onboarding

**Ne:** Yeni müşteri kaydolunca: tenant oluştur → kendi ikas/WhatsApp
bilgilerini gireceği kurulum sihirbazı. `setup_service.py` ve setup ekranı
**zaten var**; tenant'a bağlanması gerekir.

**Risk:** Düşük-orta. Mevcut setup akışı yeniden kullanılır.

**Büyüklük:** Orta.

---

## Faz 7 — Faturalandırma (opsiyonel, sonra)

**Ne:** Abonelik (Iyzico/Stripe), kullanım kotası (tenant başına aylık mesaj),
plan yönetimi. Ürün para kazanmaya başladığında eklenir.

**Bağımlılık:** Faz 1-5 tamamlanmadan anlamsız.

**Büyüklük:** Büyük (ayrı proje).

---

## Önerilen sıra ve mantık

```
Faz 0 (ORM)  →  Faz 1 (tenant/users tabloları)  →  Faz 2 (e-posta/şifre)
     →  Faz 3 (tenant ayarları)  →  Faz 4 (webhook routing)
     →  Faz 5 (izolasyon testi)  →  Faz 6 (onboarding)  →  Faz 7 (billing)
```

**Neden bu sıra:** Her faz bir öncekinin üstüne oturur. ORM olmadan izolasyon
güvensiz; tenant tablosu olmadan e-posta girişi anlamsız; ayarlar DB'de
olmadan webhook routing yapılamaz. Faz 5 (izolasyon testi) bir kilometre
taşıdır — buraya kadar sistem gerçek anlamda "çok kiracılı" olur.

## Riskin özeti

En büyük risk **veri sızıntısı** (bir müşterinin diğerini görmesi). Bunu
azaltan tek şey: Faz 0'da ORM ile merkezi filtre + Faz 5'te otomatik izolasyon
testi. Bu ikisi pazarlık konusu değildir.

İkinci risk **canlı kesinti**. Mumi şu an production'da çalışıyor. Tüm fazlar,
Mumi `tenant_id=1` olarak çalışmaya devam ederken yapılır; yeni müşteriler
sonra eklenir. Yani mevcut sistem hiç durmaz.

## Tahmini büyüklük

Bu, bugün yaptığımız üç işin (Redis, JWT, Docker) toplamından daha büyük bir
programdır. Haftalara yayılır. Ama her faz kendi başına canlıya alınabilir ve
değer üretir — hepsini bitirmeden de ilerleme görünür olur.
