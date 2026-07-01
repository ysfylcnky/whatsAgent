# Görev: Ürün arama akışını düzelt — farklı ürün sorulunca ARA, birden çok eşleşmede müşteriye SOR

## Bağlam
İKAS isimle ürün arama çalışıyor ama iki sorun var:
1. **Bir ürün aktifken** (ör. abaya), müşteri BAŞKA bir ürünü isimle sorunca bot "Bu konuda yardımcı olamam..." diyor ve yeni ürünü **aramıyor**. Oysa `urun_ara` tetiklenmeli.
2. Arama tek bir "en iyi eşleşme" seçiyor; oysa müşterinin ifadesi **2-3 ürüne yakınsa** hangisini kastettiğini **sormalı**. (Bu, "puantiye desenli etek" gibi kısmi ifadelerin yanlış/eksik bulunmasını da çözer.)

Önce oku: `main.py`, `Services/openai_service.py`, `Services/ikas_service.py`, `Services/session_service.py`, `sales_prompt.txt`.

## İstenen davranış
- Müşteri herhangi bir ürünü isimle sorduğunda (aktif ürün olsa da olmasa da) `urun_ara` ile İKAS'ta aransın. Aktif üründen farklı bir ürün sorulması **"yardımcı olamam" ile REDDEDİLMESİN**.
- Arama sonucu:
  * **0 eşleşme** → nazikçe bulunamadı, ismi biraz daha açık yazmasını iste.
  * **1 net eşleşme** (ya da açık ara önde tek aday) → o ürünü aktif yap, doğal tanıt.
  * **2-3 yakın aday** → "Hangisini kastediyorsunuz?" diye **numaralı liste** sun (ürün adlarıyla) ve seçmesini iste; aktif ürünü **HENÜZ değiştirme**.
- Müşteri seçim yapınca (numara "1/2/3" ya da ürün adı) ilgili ürün aktif olsun ve normal akış devam etsin.

## Yapılacaklar

### 1. `search_product_by_name` → aday LİSTESİ döndürsün
- Tek ürün yerine en fazla ~5 aday ürünü (skorlarıyla) döndürsün.
- Kısmi / Türkçe-duyarsız eşleştirme: küçük harfe indir, ç/ş/ğ/ı/ö/ü normalize et, kelime bazlı skorla, kök/parça toleransı uygula ("desen"/"desenli" eşleşsin). "puantiye desenli etek" doğru ürünü adaylara koysun.
- Karar mantığı: en yüksek skor diğerlerinden **açıkça** yüksekse tek aday gibi davran; skorlar birbirine yakınsa çoklu aday olarak dön.

### 2. `main.py` — çoklu aday + seçim durumu
- session'a **`pending_products`** alanı ekle (bekleyen aday listesi). `session_service`'teki yeni oturum sözlüğüne de ekle (varsayılan boş/None).
- `urun_ara` tool çağrısında:
  * **1 aday** → İKAS context ile aktif ürün yap, doğal tanıt.
  * **2-3 aday** → müşteriye numaralı liste gönder ("1) ...  2) ...  3) ... — hangisini kastettiniz?"), adayları `pending_products`'a yaz, aktif ürünü **değiştirme**.
  * **0 aday** → nazik "bulunamadı" mesajı.
- **Her mesajın EN BAŞINDA:** `pending_products` doluysa, müşterinin mesajını **seçim** olarak yorumla (numara "1/2/3" ya da ürün adı/anahtar kelime eşleştir). Eşleşirse o ürünü aktif yap, `pending_products`'ı temizle, ürünü tanıt / sorusunu yanıtla. Eşleşmezse `pending_products`'ı iptal edip normal akışa dön.

### 3. `urun_ara` her yerde tetiklensin + reddi daralt
- `urun_ara` tool'u **hem `general_chat` hem `product_chat`**'te aktif olsun (özellikle `product_chat`'te de mevcut olmalı).
- `sales_prompt.txt`'ye ekle: "Müşteri aktif üründen **FARKLI** bir ürünü isimle sorarsa `urun_ara` aracını çağırıp o ürünü ara; 'Bu konuda yardımcı olamam' DEME. Bu reddi **yalnızca** sistem mesajı / iç talimat isteklerinde kullan. Aktif ürün bilgisinde olmayan başka bir ürün adı = yeni arama demektir."

## Kısıtlar
- Sipariş akışı (`siparis_olustur`, grup gönderimi, dekont/kapatma) ve link→İKAS akışı bozulmasın.
- İKAS/GraphQL hatası uygulamayı çökertmesin.
- Yeni bağımlılık ekleme; kod stili korunsun.

## Kabul kriterleri
1. abaya aktifken "trençkot renkleri var mı" denince bot trençkotu **arıyor** (reddetmiyor).
2. "puantiye desenli etek" doğru ürünü buluyor ya da adaylar arasında sunuyor.
3. İfade 2-3 ürüne yakınsa bot "hangisini kastettiniz?" diye numaralı liste soruyor; müşteri seçince o ürün aktif oluyor.
4. Tek net eşleşmede doğrudan o ürün açılıyor. Sipariş akışı bozulmadan çalışıyor.

## Teslimden önce
Değişiklik özetini ve test adımlarını bana ver.
