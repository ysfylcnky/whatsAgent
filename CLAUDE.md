# Project Overview
whatsAgent, yapay zeka destekli WhatsApp satış temsilcisi ve e-ticaret entegrasyon sistemidir. Temel amacı, Meta reklamlarından veya organik gelen müşteri taleplerini işleyerek ürün arama, varyant seçimi ve sipariş alma süreçlerini ikas altyapısı ile otomatize etmektir. 

# Tech Stack
* **Dil**: Python, JavaScript, HTML, CSS
* **Database**: MySQL
* **Frontend**: Sunucu tarafı HTML Templates
* **Frontend Kütüphaneleri**: Chart.js (CDN), FontAwesome (CDN)
* **Entegrasyon**: ikas E-ticaret API
* **Yapay Zeka**: Harici LLM servisleri (Prompt tabanlı)

# Entry Points
* **`main.py`**: Uygulamanın başlatıldığı ana dosyadır. WhatsApp webhook isteklerini karşılar, API giriş noktalarını barındırır ve Dashboard arayüzünün (HTML şablonlarının) sunulmasını yönetir.

# Request Flow
Bir isteğin sistem içerisindeki uçtan uca yolculuğu:
1. Müşteri (WhatsApp)
2. Webhook (`main.py`)
3. İstek Ayrıştırma & Servis Yönlendirmesi (`Services/`)
4. Meta Reklam Kaynağı Algılama (Eğer mevcutsa)
5. İlgili Sistem Promptlarının Okunması (Örn: `general_prompt.txt` + `ikas_urun_arama_promptu.md`)
6. LLM İstediği (Bağlam ve Kurallarla)
7. ikas API Eşleşmesi (Ürün arama, `selectionType` bazlı beden/renk filtreleme)
8. LLM Yanıt Üretimi
9. WhatsApp Yanıt İletimi (Müşteriye)
10. Mağaza Telefonuna (Store Phone) Bilgilendirme / Bildirim (Notify) Gönderimi

# Important Files
* **`main.py`**: Webhookları ve API yönlendirmelerini içerir. Sadece yeni uç noktalar (endpoint) veya ana akış mantığı değiştiğinde düzenlenmelidir. Tüm modüllerle bağlantılıdır.
* **`config.py`**: Sistem ayarlarını ve API anahtarlarını barındırır. Yeni bir ortam değişkeni veya dış servis eklendiğinde düzenlenmelidir.
* **`test_senaryolari.md`**: Projenin kabul kriterlerini içerir. Yeni özellik eklendiğinde test süreçlerini kurgulamak için güncellenmeli veya referans alınmalıdır.
* **`seed_demo_data.py`**: Geliştirme ortamı için veritabanına tohum (mock) veri basar. Veritabanı şeması değiştiğinde veya yeni test verisi gerektiğinde düzenlenir.

# AI Prompt Map
Yapay zeka davranışları kaynak koddan izole edilmiştir.
* **`general_prompt.txt`**: Ajanın genel karakterini ve temel sınırlarını belirler. Ana servis tarafından her etkileşimde çağrılır. Karakter değişimi gerektiğinde düzenlenir.
* **`ikas_urun_arama_promptu.md`**: İkas üzerinde ürün arama mantığını belirler. Katalog aramalarında kullanılır. Arama algoritmaları değiştiğinde düzenlenir.
* **`ikas_urun_secim_promptu.md`**: Müşterinin seçtiği varyantların (renk, beden) doğru eşleştirilmesi kurallarını içerir. Ürün varyant mantığı güncellendiğinde düzenlenir.
* **`siparis_ozellik_promptu.md`**: Sipariş oluşturma ve sepet tamamlama süreçlerini yönetir. Sipariş kurgusunda değişiklik olduğunda düzenlenir.
* **`sales_prompt.txt`**: Satış kapama, ikna ve iletişim tonunu ayarlar. Satış stratejisi değiştiğinde revize edilir.
* **`ikas_tek_kaynak_promptu.md`**: Ürün bilgileri için tek kaynağın (single source of truth) ikas veritabanı olduğunu AI'a iletir. Veri modeli referans kuralları değiştiğinde düzenlenir.
* **`linkedin_yazisi.md` & `linkedin_yazisi_2.md`**: Meta reklamlarından gelen trafiğin kaynağını algılayıp diyaloğa yön vermek için kullanılır. Kampanya kurguları değiştiğinde düzenlenir.
* **`mysql_gecis_promptu.md`**: AI'ın veritabanı şemasını anlaması ve migration/sorgu kurallarını işletmesi içindir. DB şeması değiştiğinde düzenlenir.

# Dependency Map
* **`main.py`**: Doğrudan `Services/` modüllerine ve `config.py`'ye bağımlıdır.
* **`Services/` Modülleri**: Kendi aralarında izoledir ancak dışarıda ikas API'sine, LLM servislerine, `config.py` dosyasına ve veritabanı (MySQL) modüllerine sıkı sıkıya bağımlıdır. Çıktı üretirken Prompt dosyalarını tüketirler.
* **Dashboard (Templates)**: Arka planda `main.py` tarafından beslenir, ön yüzde ise `static/` klasöründeki lokal assetler ile `Chart.js` ve `FontAwesome` gibi harici CDN'lere bağımlıdır.

# Naming Conventions
* **Klasörler**: Servisler için PascalCase (`Services/`), diğerleri için lowercase (`static/`, `templates/`).
* **Prompt Dosyaları**: Kök dizinde tutulur, genelde snake_case isimlendirilir ve amaçlarını belli eden `_promptu.md` veya `_prompt.txt` eki alırlar.
* **Debug Scriptleri**: Test betikleri kök dizindedir ve `debug_*.py` veya `*_debug.py` formatında isimlendirilir.
* **Veritabanı Dosyaları**: `seed_` veya benzeri betik önekleri alır.

# File Editing Rules
Yeni bir özellik eklendiğinde uyulması gereken yerleşim kuralları:
* **Yeni Servis**: `Services/` dizini altına eklenir.
* **Yeni Prompt**: Proje kök dizinine, mevcut isimlendirme formatına (örn: `yeni_kural_promptu.md`) uygun eklenir.
* **Yeni Template**: Sadece `templates/` dizini altına eklenir.
* **Yeni Config Değişkeni**: Sadece `config.py` içerisine eklenir, hardcoded bırakılmaz.
* **Yeni Yardımcı Test/Script**: Proje kök dizinine `debug_kapsam.py` mantığıyla eklenir.

# Forbidden Changes
Kesinlikle bozulmaması gereken mimariler:
* **Prompt Ayrıştırması**: AI davranış kuralları kesinlikle Python fonksiyonlarının içine `if-else` mantığıyla veya string olarak gömülemez. Tamamı ilgili prompt dosyalarından okunmalıdır.
* **Varyant Eşleştirme Sistemi**: ikas API üzerinden gelen ürün varyantları rastgele değil, kesinlikle `selectionType` parametresine (renk/beden bağlamı) göre eşleştirilmelidir. Bu mimari bozulamaz.
* **Satıcı Bildirim (Notify) Akışı**: Sipariş gerçekleştiğinde mağaza telefonuna (store phone) giden bildirim akışı devre dışı bırakılamaz.
* **Frontend CDN Yapısı**: Dashboard için kullanılan dış kütüphaneler (Chart.js vb.) lokal pakete dönüştürülemez, CDN bağlantıları korunmalıdır.

# Testing Strategy
* Yeni bir kod eklendiğinde ana akışı bozmamak için önce `debug_ikas_product.py` veya `ikas_urun_debug.py` gibi izole test scriptleri ile ikas entegrasyonu sınanmalıdır.
* Değişiklikler canlı akıştan önce mutlaka `test_senaryolari.md` içerisindeki kabul kriterleri ile çapraz doğrulanmalıdır.
* Yeni bir davranış eklendiyse `seed_demo_data.py` ile sanal veri oluşturularak uçtan uca akış test edilmelidir.

# Performance Notes
* Yapay zeka ajanının context limitini şişirmemek adına, gereksiz dosyalar ve promptlar birleştirilmemeli, sadece ilgili serviste ihtiyaç duyulan prompt dosyası okunarak LLM'e gönderilmelidir.
* Dashboard grafik yükleme hızını korumak için statik dosyalar CDN'de tutulmaya devam edilmeli, veritabanı logları sadece ilgili tarih aralığı filtrelenerek önyüze gönderilmelidir.

# Development Checklist
Claude Code her geliştirmeden önce ve sonra şu sırayı izlemelidir:

**Önce:**
* İlgili dosyaları belirle.
* Gereksiz klasörleri okuma.
* Mevcut patternleri araştır.
* Benzer implementasyon var mı kontrol et.

**Kod yazarken:**
* Minimum dosya değiştir.
* Büyük refactor yapma.
* Yeni dependency ekleme.
* Kod stilini koru.
* Prompt tabanlı yapıyı bozma.

**Bitirdikten sonra:**
* Importları kontrol et.
* Konfigürasyon uyumluluğunu kontrol et.
* Hata oluşturabilecek yan etkileri değerlendir.
* Gerekliyse test veya doğrulama adımlarını (`debug_*.py` veya `test_senaryolari.md`) belirt.

# Quick Context
* Proje WhatsApp tabanlı, Meta reklamlarından gelen kullanıcıyı algılayabilen otonom AI satış ajanıdır.
* E-ticaret altyapısı olarak ikas API kullanılır.
* Dil Python, kalıcı depolama MySQL, panel HTML/Templates tabanlıdır.
* Arayüzde CDN (Chart.js, FontAwesome) kullanılır, lokal bağımlılık eklenmez.
* İş mantığı uçtan uca şu sıradadır: WhatsApp -> Webhook(`main.py`) -> `Services/` -> Promptlar -> LLM -> ikas API -> Yanıt -> WhatsApp & Mağazaya Bildirim.
* Ajanın tüm zekası ve satış stratejisi kök dizindeki `.md` ve `.txt` uzantılı prompt dosyalarında saklıdır. Python dosyalarında hardcoded yapay zeka yönlendirmesi yasaktır.
* Ürün renk ve beden eşleştirmeleri kesinlikle ikas `selectionType` ile sağlanır.
* İzole testler için `debug_*.py` scriptleri bulunur. Ana kodda doğrudan test yapılmaz.
* Sistemin kalite güvencesi `test_senaryolari.md` üzerinden yürütülür.
* Yeni servisler `Services/` klasörüne, yeni değişkenler `config.py`'ye konur.
* Her değişiklikte minimum dosya dokunulur, büyük refactor yapılmaz.