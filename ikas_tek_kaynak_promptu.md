# Görev: __NEXT_DATA__ link kazımasını tamamen kaldır, tüm ürün verisini İKAS API'dan al

## Bağlam
Şu an ürünler iki yoldan tanınıyor: (1) **link** → `Services/product_service.py` içindeki `__NEXT_DATA__` kazıma, (2) **isim** → `Services/ikas_service.py` İKAS API. Artık **(1) tamamen kaldırılacak**; TÜM ürün verisi İKAS API'dan gelecek.

**Link desteği KALACAK**, ama link geldiğinde sitede kazıma yapmak yerine linkin **slug'ından ürün adı çıkarılıp İKAS'ta aranacak**. Yani hem link hem isim tek bir yola (İKAS araması) akacak.

Başlamadan oku: `main.py`, `Services/product_service.py`, `Services/ikas_service.py`, `Services/session_service.py`, `config.py`.

## Yapılacaklar

### 1. Link kazımasını kaldır
- `product_service.py`'deki `__NEXT_DATA__` / `requests.get` tabanlı fonksiyonları (`get_product_context`, `build_ai_context`, `get_cached_ai_context`) **kaldır**. Bu dosyayı ya tamamen sil ya da içini boşaltıp yalnızca İKAS'a yönlendiren ince bir katman bırak — hangisi daha temizse onu yap.
- Bu fonksiyonlara olan **tüm importları** (özellikle `main.py`) güncelle/kaldır.
- `/product-context` endpoint'i bu kazıma fonksiyonlarını kullanıyorsa: ya kaldır ya da İKAS aramasını kullanacak şekilde güncelle.
- Projede `requests.get` ile site kazıma ve `__NEXT_DATA__` ayrıştırma **hiç kalmasın**.

### 2. Link → İKAS araması
`main.py`'de mesajda URL tespit edilince (mevcut `extract_url` korunur):
- Linkin **son yol parçasını (slug)** al. Örn: `https://.../yeni-sezon-liya-puantiye-etek` → `yeni-sezon-liya-puantiye-etek`. (Varsa query string `?...` ve sondaki `/` temizlensin.)
- Tire/alt çizgileri boşluğa çevir → `yeni sezon liya puantiye etek`.
- Bunu `ikas_service.search_product_by_name`'e ver, İKAS'ta ara.
- Bulunursa aktif ürün yap (bkz. madde 3). Bulunamazsa nazikçe ürün ismini yazmasını iste.

### 3. Tek kaynak: İKAS context (takip soruları hatasını da çözer)
- Artık her ürün İKAS'tan geliyor. Aktif ürün için takip sorularında (fiyat, beden, renk) **LİNK parser'ı ASLA çağrılmasın**; ürün bulunduğunda `build_ikas_ai_context` ile üretilip session'a saklanan context'i kullan (gerekirse `ikas_service`'te ürün **id** ile yeniden çekme fonksiyonu ekle).
- Bu, önceki **"Ürün bilgisi alınırken hata oluştu"** hatasını da çözer (o hata, İKAS ürünü aktifken link parser'ının çağrılmasından kaynaklanıyordu).
- session'daki "source" ("link"/"ikas") ayrımına artık gerek yok (tek kaynak İKAS); varsa sadeleştir. `active_url` anahtarı olarak İKAS ürün id'sini kullanmaya devam et.

### 4. Arama kalitesini iyileştir (kısmi / anahtar kelime)
`search_product_by_name` kısmi ve Türkçe-duyarsız eşleşsin:
- İKAS `searchProducts` (tam metin) sorgusunu kullan; yoksa `listProduct` ile aday ürünleri çekip Python'da eşle.
- Eşleştirme: küçük harfe indir, Türkçe karakterleri normalize et (ç→c, ş→s, ğ→g, ı→i, ö→o, ü→u), sorgudaki anlamlı kelimelerin üründe geçme oranına göre skorla, en yüksek skorlu ürünü seç; hiç anlamlı kelime eşleşmiyorsa "bulunamadı" say.
- Böylece "puantiye desenli etek" → "Yeni Sezon Trend Liya Puantiye Desen Etek" bulunur.
- Birden fazla eşleşmede **en iyi eşleşme** otomatik seçilsin (mevcut karar).

## Kısıtlar
- Sipariş akışı (`siparis_olustur`, grup gönderimi, dekont/kapatma) ve `urun_ara` aracı **aynen** çalışsın.
- İKAS/GraphQL hatası uygulamayı **çökertmesin**; müşteriye nazik mesaj, logda detay.
- Yeni bağımlılık ekleme. Mevcut kod stili (Türkçe yorum, yapı) korunsun.

## Kabul kriterleri
1. Müşteri ürün ismini (kısmi de olsa) yazınca İKAS'tan bulunuyor, aktif oluyor; takip soruları (beden/renk/fiyat) hatasız yanıtlanıyor.
2. Müşteri ürün LİNKİ gönderince, slug'dan isim çıkarılıp İKAS'ta bulunuyor ve aynı şekilde çalışıyor.
3. Projede `__NEXT_DATA__` / site kazıma kodu kalmadı; tüm ürün verisi İKAS'tan geliyor.
4. Sipariş akışı bozulmadan çalışıyor.

## Teslimden önce
Değişiklik özetini, kaldırılan/boşaltılan dosya ve fonksiyonları, ve test adımlarını bana ver.
