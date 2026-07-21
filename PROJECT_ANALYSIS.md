1. Projenin Amacı
Bu proje ne yapıyor? Proje, WhatsApp üzerinden Meta reklamlarından gelen veya organik olarak ulaşan müşterilerle 7/24 iletişim kuran, otonom bir yapay zeka (AI) satış asistanıdır
. Müşterilerin ürün (isim veya link ile), stok, beden, renk ve fiyat sorularını canlı e-ticaret (ikas) altyapısından çekerek yanıtlar ve uçtan uca sipariş oluşturur
. Sesli mesajları anlayabilir (Whisper) ve dashboard üzerinden ROI/tasarruf raporlaması sunar
.
Hangi problemi çözüyor? E-ticaret satıcılarının Meta reklamlarına harcadıkları bütçe sonucu oluşan WhatsApp trafiğine geç yanıt verilmesi (veya hiç verilmemesi) sebebiyle kaçan satışları engeller. Manuel ve tekrarlayan "M beden var mı?", "Fiyatı ne?" gibi soruları yanıtlayarak personel yükünü ve maliyetini ortadan kaldırır
.
Hedef kullanıcı kitlesi kim? Meta (Facebook/Instagram) reklamları üzerinden WhatsApp'a trafik çeken, altyapı olarak "ikas" kullanan KOBİ ve butik tarzı e-ticaret satıcılarıdır
.
2. Genel Mimari
Kullanılan teknolojiler: Backend için Python ve FastAPI
, veritabanı için MySQL (mysql-connector-python ile raw SQL)
, LLM ve transkripsiyon için OpenAI API (gpt-4.1-mini, Whisper)
, e-ticaret entegrasyonu için ikas GraphQL API
, Frontend için Jinja2 template'leri, Chart.js ve vanilla JavaScript
. Altyapı olarak Docker kullanılmaktadır
.
Katmanlı mimari: Geleneksel monolitik bir yapı mevcuttur. İstekler main.py (Controller/Router) üzerinden alınır, iş mantığı Services/ dizinindeki servislere devredilir
. AI prompt'ları koda gömülmemiş, ayrı .txt ve .md dosyalarında tutularak izole edilmiştir
.
Dosya organizasyonu: Kök dizinde yapılandırma (config.py, .env), başlatıcı (main.py) ve prompt'lar bulunur. Services/ iş mantığını, templates/ ve static/ ise sunucu tarafında render edilen (SSR) önyüzü barındırır
.
Veri akışı: Müşteri mesaj atar -> WhatsApp Cloud API Webhook (main.py) -> İlgili servis (openai_service.py vb.) -> LLM Prompt ile karar -> (Gerekirse) Tool Calling ile ikas_service.py üzerinden API sorgusu -> Yanıt üretimi -> Müşteriye ve Mağazaya Bildirim -> MySQL'e loglama
.
SaaS Olarak Değerlendirme & Servis İlişkileri: Mimari şu an Single-Tenant (Tek Kiracılı) olarak tasarlanmıştır. Tüm sistem tek bir .env dosyasındaki mağaza bilgilerine (IKAS_CLIENT_ID, OPENAI_API_KEY vb.) bağlıdır
. Gerçek bir SaaS olabilmesi için Multi-Tenant (Çok Kiracılı) mimariye geçmesi şarttır.
3. Modül Analizi
Services/ Klasörü:
Görevi: İş mantığını yönetmek (ikas_service, openai_service, order_service, vb.)
.
Güçlü yönleri: Servislerin (dosyaların) kendi içlerinde izole edilmiş olması iyi bir başlangıç. Dış API'ler (ikas, OpenAI) ayrı dosyalarda tutulmuş
.
Eksikleri: Dependency Injection (Bağımlılık Enjeksiyonu) kullanılmamış. Servisler doğrudan config.py üzerinden global state okuyor
. Session yönetimi bellek üzerinde (chat_sessions dict) yapılıyor
.
Refactor İhtiyacı: Bellek içi chat_sessions acilen Redis gibi dağıtık bir önbelleğe taşınmalı. Global config okumaları, Tenant tabanlı yapılandırma okumalarına dönüştürülmeli.
main.py:
Görevi: Webhook karşılayıcı, API endpoint'leri ve UI render işlemleri
.
Eksikleri: "God Object" (Her şeyi yapan dosya) antipattern'ine doğru ilerliyor. Hem UI rotalarını, hem Webhook'ları, hem de auth logic'ini barındırıyor
.
Refactor İhtiyacı: FastAPI APIRouter kullanılarak UI rotaları, Webhook rotaları ve Admin rotaları ayrı modüllere bölünmeli.
static/ & templates/:
Görevi: Dashboard arayüzünü sunmak
.
Eksikleri: Modern bir SaaS için Jinja2 ile SSR (Server Side Rendering) kullanmak ölçeklemeyi ve UI geliştirme hızını yavaşlatır.
Refactor İhtiyacı: API First yaklaşıma geçilip, frontend React, Vue veya Next.js gibi ayrı bir SPA (Single Page Application) olarak ayrılmalı.
4. Veritabanı
Şema Analizi & İlişkiler: usage_logs, conversations, customers, orders, settings tabloları olduğu görülüyor
. Ancak kod tabanında bir ORM kullanılmadan (SQLAlchemy vb.) mysql-connector-python ile raw SQL yazılmaktadır
.
Eksik Tablolar: SaaS için en kritik eksik tenants (veya shops), users (RBAC için), ve subscriptions (ödeme planları) tablolarıdır. Tüm mevcut tabloların tenant_id foreign key'ine sahip olması gerekir.
Performans Önerileri:
Connection Pooling (Bağlantı Havuzu) kurulmuş olması olumlu
.
Log bazlı sorgularda (Dashboard grafikleri için 14 günlük veriler
) timestamp üzerinde kesinlikle index olmalıdır.
Raw SQL sürdürülebilirlik açısından teknik borçtur. Kesinlikle SQLAlchemy veya SQLModel gibi bir ORM'e geçilmelidir.
5. API Analizi
Endpoint Yapısı: REST standartlarına kısmen uyulmuş. GET ile sayfa dönülmesi, POST ile webhook ve ayar güncellenmesi yapılıyor
. Ancak endpoint'ler modüler değil.
Güvenlik & Validation: Pydantic ile input validation yapıldığına dair bir kanıt yok; manuel tip kontrolleri (örn. float parse) yapılmış
. Dashboard için HTTP Basic Auth kullanılmış
. Bu SaaS için kabul edilemez bir güvenlik açığıdır.
Hata Yönetimi: Veritabanı bağlantı hatalarının uygulamayı çökertmemesi (swallow edilmesi) sağlanmış
. Ancak genel ve standart bir Exception Handler (FastAPI middleware seviyesinde) eksik.
Eksik Endpointler: JWT tabanlı Auth endpoint'leri, Tenant yönetim API'leri, faturalandırma (Stripe/Iyzico) endpoint'leri.
6. Güvenlik Analizi
Authentication & Authorization: Sadece DASHBOARD_USER ve PASSWORD ile Basic Auth var
. Rol bazlı erişim kontrolü (RBAC) yok. JWT veya OAuth2 entegrasyonu acilen gereklidir.
Rate Limit: Gelen Webhook'lar veya Admin API'leri için herhangi bir Rate Limiting belirtisi yok. (Sadece OpenAI API limitlerine karşı hata yakalama var
). Kötü niyetli bir kullanıcı sisteme sonsuz webhook atarak LLM faturasını patlatabilir.
Input Validation & SQL Injection: SQL tarafında parametrik (%s) yapı kullanılması SQL Injection'ı önler
. Ancak Pydantic modelleriyle gelen verinin sanitize edilmesi şarttır. XSS'e karşı UI'da HTML karakterlerinin escape edildiği belirtilmiş
.
Secret Yönetimi: Sırlar .env dosyasından okunuyor
. Güvenli görünse de production'da AWS Secrets Manager veya HashiCorp Vault gibi araçlar düşünülmelidir.
7. Performans Analizi
Cache: İkas aramaları ve ürün context'i için bellek içi önbellekleme (ikas_search_cache, CACHE_TTL) yapılmış
.
Bellek Kullanımı & Ölçeklenebilirlik (En büyük sorun): chat_sessions dict'i, _setup_complete_cache gibi global değişkenler uygulamanın durumunu (state) RAM'de tutuyor
. Bu uygulama Docker ile birden fazla instance'a (replica) çıkarıldığında, oturumlar instance'lar arası kaybolacaktır (Stateful yapı). Uygulama Stateless hale getirilmeli ve session'lar Redis'e taşınmalıdır.
LLM Yükü: Gereksiz token harcamasını önlemek için MAX_HISTORY (12 mesaj) limiti konulmuş
, bu maliyet ve context şişmesi açısından başarılı bir optimizasyon
.
8. Kod Kalitesi
Clean Code & SOLID: LLM prompt'larının Python kodundan çıkarılıp .txt ve .md dosyalarına alınması (Open-Closed principle açısından) muazzam bir pratik
. Ancak main.py Single Responsibility (Tek Sorumluluk) kuralını ihlal ediyor
.
DRY & İsimlendirme: Türkçe yorum satırları, net ve anlaşılır Pythonik isimlendirmeler (snake_case fonksiyonlar) kullanılmış
. SQL sorguları kodun içine Hardcoded yazılmış, bu da kod tekrarı (DRY ihlali) yaratma potansiyeline sahip
.
9. Teknik Borç Listesi (Önem Sırasına Göre)
Kritik: State'in (Session ve Setup Cache) in-memory tutulması (Ölçeklenmeyi engeller).
Kritik: Dashboard'un HTTP Basic Auth ile korunması (Ciddi güvenlik riski).
Kritik: Webhook endpoint'lerinde LLM kaynaklı maliyet ataklarına karşı Rate Limiting olmaması.
Yüksek: Raw SQL kullanımı (ORM eksikliği sürdürülebilirliği zorlaştırır).
Yüksek: main.py içerisindeki spagetti API ve Webhook routing yapısı.
Orta: Frontend'in Jinja2 ile SSR olarak sunulması.
10. Eksik Özellikler (SaaS Dönüşümü İçin)
Multi-Tenancy (Çok Kiracılı Yapı): Her müşterinin kendi mağazasını, kendi API key'ini (veya sistemin global key'ini kotalı şekilde) kullanabileceği veritabanı izolasyonu.
Faturalandırma (Billing): Kullanım bazlı (token/mesaj sayısına göre) veya aylık sabit abonelik için Stripe/Iyzico entegrasyonu.
Kullanıcı ve Rol Yönetimi: Mağaza sahipleri ve çalışanları için yetkilendirme sistemi (RBAC).
Gelişmiş Rate Limiting & Quota Management: Her müşterinin aylık bot kullanım kotasını aşmasını engelleyecek altyapı.
Platform Çeşitliliği: Sadece İkas değil, Shopify, Ticimax, WooCommerce adaptörleri.
11. DevOps
Dockerfile ve docker-compose.yml hazır edilmiş
. Geliştirme/test için yeterli.
Eksiklikler:
Production Hazırlığı: CMD ["uvicorn", "main:app"...] kullanılmış
. Production'da Gunicorn (Uvicorn worker'ları ile) kullanılmalıdır.
Logging: Sadece print ve standart console loglama yapılıyor
. Merkezi bir ELK (Elasticsearch, Logstash, Kibana) veya Datadog entegrasyonu (JSON formatında log) şart.
CI/CD: Herhangi bir GitHub Actions veya GitLab CI pipeline'ından bahsedilmiyor.
Monitoring: Sadece dashboard üzerinde metrik var
, sistem metrikleri (CPU, RAM, API latencies) için Prometheus & Grafana entegrasyonu eksik.
12. Test Altyapısı
Mevcut Durum: Kod tabanında manuel test scriptleri (debug_ikas_product.py)
 ve markdown tabanlı kabul kriterleri listesi (test_senaryolari.md) var
.
Kritik Eksik: Otomatize edilmiş Unit Test (pytest), Integration Test ve E2E test sıfır. Bu seviyede bir SaaS için otomatize testin olmaması her deploy'da sistemin çökme riskini barındırır. Acilen LLM yanıtlarını mocklayan ve veritabanı işlemlerini test eden CI süreçleri yazılmalıdır.
13. Önceliklendirilmiş Roadmap
🔴 Kritik (Hemen Yapılmalı - Bloklayıcı)
~~Stateless Mimariye Geçiş: chat_sessions belleğinden Redis'e geçiş.~~ ✅ **TAMAMLANDI (2026-07-21)** — `Services/session_store.py` eklendi: SessionStore repository (Redis + bellek içi fallback), Identity Map + Unit of Work cephesi. `main.py` global dict'ten arındırıldı, oturum TTL'i Redis'e devredildi. Doğrulama: `debug_session_store.py` (25/25). Kalan in-memory state: `ikas_search_cache` (ikas_service.py) ve `_setup_complete_cache` (setup_service.py) — bunlar salt-okunur önbellek olduğu için ölçeklemeyi bloklamaz, ancak orta vadede Redis'e taşınmalıdır.
Multi-Tenancy Veritabanı Güncellemesi: Tablolara tenant_id eklenmesi ve ortam değişkenlerinden (.env) DB okumasına geçiş. (Zorluk: Yüksek | Fayda: Projeyi tek kullanıcılıktan SaaS'a dönüştürür).
Güvenlik - JWT Auth: Basic Auth kaldırılarak JWT/OAuth2 implementasyonu. (Zorluk: Orta | Fayda: Güvenlik açığını kapatır).
🟠 Yüksek (Kısa Vadeli Hedefler)
ORM Entegrasyonu: Raw SQL yerine SQLAlchemy (veya SQLModel) entegrasyonu. (Zorluk: Orta | Fayda: Sürdürülebilirlik, kolay migration ve kod kalitesi).
Test Otomasyonu: pytest ile birim ve entegrasyon testlerinin yazılması ve CI/CD pipeline'ına eklenmesi. (Zorluk: Yüksek | Fayda: Regresyon hatalarını sıfıra indirir).
Routing Modülerizasyonu: main.pynin FastAPI APIRouterlar ile parçalanması. (Zorluk: Düşük | Fayda: Kod okunabilirliği ve takım çalışması).
🟡 Orta (Orta Vadeli Hedefler)
Rate Limiting: IP veya Tenant bazlı Redis rate limiting. (Zorluk: Düşük | Fayda: LLM fatura saldırılarını önler).
Abonelik (Billing) Entegrasyonu: Kullanıma (usage) dayalı SaaS ödeme altyapısı kurulması. (Zorluk: Yüksek | Fayda: Ürünün para kazanmasını sağlar).
🟢 Düşük (Uzun Vadeli Hedefler)
Frontend Değişimi: Jinja2'den React/Next.js'e geçiş. (Zorluk: Yüksek | Fayda: Modern, hızlı ve mobil uyumlu yönetim paneli).
Yeni Platform Destekleri: Shopify vb. adaptörlerin Services/ altına eklenmesi. (Zorluk: Orta | Fayda: Pazar payını büyütür).
14. Genel Değerlendirme
Proje Puanı: 6.5 / 10 (Harika bir MVP (Minimum Viable Product), ancak SaaS olarak prodüksiyona hazır bir temel değil.)
Güçlü Yönleri: LLM entegrasyonu (Tool Calling ile e-ticaret bağlantısı, Whisper kullanımı) çok başarılı kurgulanmış
. AI'ın iş mantığının (prompts) koda gömülmeyip dışarıdan beslenmesi harika bir mühendislik kararı
. Sorunu (geç yanıtlanan WhatsApp mesajları) çok net tespit edip, işe yarar, gerçek bir çözüm üretmiş
.
En Büyük Riskler: In-memory session'lar yüzünden sistemin yatayda (horizontal) kesinlikle ölçeklenemeyecek olması. Test otomasyonunun hiç olmaması (sürüm atarken manuel teste mahkumiyet). Basic Auth ve Rate Limit eksikliği sebebiyle güvenlik zafiyeti.
En Önemli Geliştirme Fırsatları: Eğer altyapı Multi-Tenant ve Stateless hale getirilirse, bu ürün pazarın çok net bir kanayan yarasına parmak basıyor. Faturalandırma sistemi eklenerek doğrudan yüksek kâr marjlı bir SaaS şirketine evrilebilecek potansiyele sahip.