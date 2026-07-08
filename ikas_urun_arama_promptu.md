# Görev: İKAS API ile ürün ismiyle ürün tanıma (mevcut link akışına EK olarak)

## Bağlam
Bu WhatsApp satış botu şu an ürünleri yalnızca **link** üzerinden tanıyor: müşteri ürün linki gönderince `Services/product_service.py` sitenin `__NEXT_DATA__` JSON'ından parse edip bir `ai_context` çıkarıyor (renk, beden, stok, fiyat).

Site **İKAS** altyapısında. Ürün + envanter **okuma** izinli İKAS API bilgileri mevcut. Amaç: müşteri ürünü **isimle** de sorabilsin. İsimle arama İKAS Admin GraphQL API üzerinden yapılacak.

Kararlar:
- **Link akışı AYNEN korunacak**, isim akışı EK olarak gelecek.
- Model, müşterinin bir ürünü isimle sorduğunu anlayınca bir **`urun_ara`** aracı (tool calling) çağıracak (sipariş akışındaki tool mantığının aynısı).
- Birden fazla ürün eşleşirse **en iyi eşleşme otomatik seçilecek**.
- Bulunan ürün, mevcut `ai_context` yapısına eşlenip **aktif ürün** yapılacak; sonraki sorular ("38 var mı", "fiyatı ne") mevcut akışla yanıtlanacak.

Başlamadan oku: `main.py`, `Services/product_service.py`, `Services/session_service.py`, `Services/openai_service.py`, `Services/order_service.py`, `config.py`.

## İKAS API mekaniği (resmî dokümandan doğrulandı)
- **Token:** `POST https://<IKAS_STORE_NAME>.myikas.com/api/admin/oauth/token`, `content-type: application/x-www-form-urlencoded`, gövde: `grant_type=client_credentials`, `client_id`, `client_secret`. Yanıt: `access_token` (Bearer), `expires_in=14400` (4 saat).
- **GraphQL:** `POST https://api.myikas.com/api/v1/admin/graphql`, header `Authorization: Bearer <token>`, gövde `{"query": "...", "variables": {...}}`.
- **Ürün arama:** `searchProducts(input: SearchInput!)` (tam metin arama) veya `listProduct(name: StringFilterInput, pagination: PaginationInput)`. Ürün alanları: `name`, `variants`, `productVariantTypes` (Renk/Beden tipleri ve `values`), `totalStock`; varyantlarda fiyat (sellPrice/discountPrice) ve stok bilgisi bulunur.
- **Kesin alan adlarını** (Variant içindeki `prices`, `sellPrice`, `discountPrice`, stok alanı, `variantValues`; ayrıca `StringFilterInput` ve `SearchInput` operatörleri) uygulamadan önce şu dokümanlardan WebFetch ile doğrula:
  - https://ikas.dev/docs/api/admin-api/products
  - https://ikas.dev/docs/api/admin-api/variant-type
  - Bu sayfalardaki `Variant`, `StringFilterInput`, `SearchInput` type-definition linkleri.

## Yapılacak değişiklikler

### 1. `config.py`
Ekle:
```python
IKAS_STORE_NAME = os.getenv("IKAS_STORE_NAME")
IKAS_CLIENT_ID = os.getenv("IKAS_CLIENT_ID")
IKAS_CLIENT_SECRET = os.getenv("IKAS_CLIENT_SECRET")
```
`.env`'e eklenecekler (kullanıcı dolduracak): `IKAS_STORE_NAME`, `IKAS_CLIENT_ID`, `IKAS_CLIENT_SECRET`.

### 2. Yeni dosya: `Services/ikas_service.py`
- **Token yönetimi:** access token'ı bellekte cache'le; süresi dolmadan (örn. bitişten ~5 dk önce) yenile. Token endpoint yukarıdaki gibi.
- **`_graphql(query, variables=None)`:** GraphQL endpoint'ine Bearer token ile POST atan yardımcı; timeout ve hata yönetimi olsun. `errors` dönerse logla.
- **`search_product_by_name(name)`:** İKAS'ta isimle ürün ara. **Kısmi eşleşmeyi** destekleyen sorguyu kullan (`searchProducts` tercih; olmazsa `listProduct(name:...)`). Birden çok sonuç gelirse **en iyi eşleşmeyi** seç: basit bir skorla (tam eşleşme > baştan başlayan > içeren; büyük/küçük harf ve Türkçe karakter duyarsız). Bulunamazsa `None` dön.
- **`build_ikas_ai_context(product)`:** İKAS ürününü, `product_service.build_ai_context`'in döndürdüğü **AYNI** sözlük yapısına eşle:
  ```python
  {
    "name": ...,
    "price": ...,
    "discount_price": ...,
    "available_colors": [...],
    "available_sizes": [...],
    "variants": [{"color": ..., "sizes": {beden: stok}}]
  }
  ```
  Renk/Beden'i `productVariantTypes`'tan; renk×beden→stok ile fiyat/indirim'i `variants`'tan çıkar. (Tip isimleri "Renk/Color", "Beden/Size" varyasyonlarını tolere et.)
- **Cache:** sonucu `CACHE_TTL` kadar cache'le (isim→context), gereksiz API çağrısını önle. `product_service.get_cached_ai_context`'teki cache desenini örnek al.

### 3. Yeni tool: `urun_ara`
`Services/order_service.py` (veya `ikas_service.py`) içine OpenAI tool tanımı ekle:
- `name: "urun_ara"`, parametre `{"urun_ismi": "string"}`.
- Açıklama: "Müşteri bir ürünü İSİMLE sorduğunda/aradığında (link vermeden) çağır. Ürün fiyat/renk/beden/stok bilgisi gerektiğinde bunu kullan."

### 4. `Services/openai_service.py`
- `urun_ara` tool'unu **hem `general_chat` hem `product_chat`**'e ekle. `siparis_olustur` yalnızca `product_chat`'te kalsın.
  - `product_chat` tools: `[URUN_ARA_TOOL, SIPARIS_TOOL]`
  - `general_chat` tools: `[URUN_ARA_TOOL]` (şu an tool'suz; tools desteği ekle)
- `_create_chat` zaten `tool_call` döndürüyor; birden fazla tool tipini bozmadan koru.

### 5. `main.py` — `urun_ara` akışı
Hem genel hem ürün akışında dönen `tool_call` `"urun_ara"` ise:
- `ikas_service.search_product_by_name(urun_ismi)` ile ara.
- **Bulunduysa:** `build_ikas_ai_context` ile context çıkar; session'a **aktif ürün** olarak kaydet (mevcut `store_product` + `active_url` mantığıyla; anahtar olarak İKAS ürün **id**'sini kullan ve `active_url`'i bu anahtara ayarla). Ardından ürünü **doğal bir dille** tanıt: tool sonucunu (ürün özeti) modele geri verip **ikinci bir tamamlama çağrısı** yap ki model müşterinin asıl sorusunu da yanıtlasın (ör. "Buldum 😊 Siyah triko kazak 299 TL, S-M-L bedenleri mevcut"). (Bu round-trip karmaşık gelirse: ürünü aktif yap ve kısa, doğal bir tanıtım mesajı gönder.)
- **Bulunamadıysa:** nazikçe bulunamadığını söyle, ismi tekrar yazmasını ya da ürün linkini göndermesini rica et.

Link akışı ve `siparis_olustur` akışı **AYNEN** korunsun.

## Kısıtlar
- Mevcut **link tabanlı** tanıma bozulmasın.
- İKAS token/GraphQL hataları uygulamayı **çökertmesin**; hata olursa müşteriye nazik bir mesaj, logda detay.
- Sipariş akışı (`siparis_olustur`, grup gönderimi, dekont/kapatma) etkilenmesin.
- Yeni bağımlılık ekleme (`requests` zaten var). Kod stili: Türkçe yorum, mevcut yapı, fonksiyon imzalarını koru.

## Kabul kriterleri
1. Müşteri link olmadan ürün ismi yazınca bot İKAS'tan ürünü bulup fiyat/renk/beden bilgisini doğal şekilde veriyor ve o ürün **aktif** oluyor; sonraki "38 var mı / fiyatı ne" soruları doğru yanıtlanıyor.
2. Ürün linki gönderme akışı hâlâ çalışıyor.
3. Ürün bulunamazsa nazik bir mesaj; uygulama çökmüyor.
4. Sipariş akışı bozulmadan çalışıyor.

## Teslimden önce
Kullandığın GraphQL sorgusunu (arama + varyant/stok/fiyat alanları) ve `.env`'e eklemem gereken `IKAS_*` satırlarını bana ver. Test adımlarını da yaz.
