# Görev: WhatsApp botuna sipariş alma + siparişi WhatsApp grubuna iletme özelliği

## Bağlam
Bu, FastAPI tabanlı bir WhatsApp yapay zeka satış asistanı. Mevcut akış: müşteri ürün linki gönderir, bot ürün hakkında bilgi verir (`product_chat`, `sales_prompt.txt`). Token/maliyet loglaması MySQL'e yapılır.

Eklenecek özellik: Müşteri sipariş vermek isteyince bot gerekli bilgileri sohbet ederek toplar, sipariş özetini çıkarıp müşteriden **onay alır**, müşteri onaylayınca siparişi mağaza **WhatsApp grubuna** iletir. Böylece mağaza çalışanları kargoyu hazırlar.

Başlamadan önce şu dosyaları oku ve mevcut yapıyı anla: `main.py`, `Services/openai_service.py`, `Services/session_service.py`, `Services/whatsapp_service.py`, `config.py`, `sales_prompt.txt`.

## Yaklaşım
OpenAI **tool/function calling** kullan. Modele `siparis_olustur` adında bir tool ver. Model bilgileri doğal sohbetle toplar, özetler, onay ister; müşteri **açıkça onayladıktan sonra** tool'u çağırır. Backend bu tool çağrısını yakalayıp siparişi gruba gönderir. **Onaydan önce tool çağrılmamalı.** Model `gpt-4.1-mini` (tool calling destekliyor).

## Toplanacak sipariş alanları (hepsi zorunlu)
`ad_soyad`, `telefon`, `teslimat_adresi`, `urun`, `renk`, `beden`, `adet`, `odeme_sekli` (yalnızca "Kapıda Ödeme" veya "Havale/EFT").

---

## Yapılacak değişiklikler

### 1. Yeni dosya: `Services/order_service.py`
İçinde şu iki şey olsun:

`SIPARIS_TOOL` — OpenAI tool tanımı. Fonksiyon adı `siparis_olustur`, açıklamasında "müşteri özeti AÇIKÇA onayladıktan sonra, tüm alanlar tamamlanınca çağrılır; onaydan önce ASLA çağırma" yazsın. Parametreler yukarıdaki 8 alan; `odeme_sekli` için `enum: ["Kapıda Ödeme", "Havale/EFT"]`; `adet` integer; hepsi `required`.

`format_order_message(order)` — gruba gidecek mesajı biçimlendirir. "Kapıda Ödeme" seçilmişse ödeme satırına "(+90 TL ek ücret)" ekle. Şu formatı kullan:
```
🛒 *YENİ SİPARİŞ*
🕒 <gün.ay.yıl saat:dakika>

👤 Ad Soyad: ...
📞 Telefon: ...
📍 Adres: ...

🛍 Ürün: ...
🎨 Renk: ...
📏 Beden: ...
🔢 Adet: ...

💳 Ödeme: ...
```

### 2. `config.py`
WhatsApp bölümüne ekle:
```python
WHATSAPP_GROUP_ID = os.getenv("WHATSAPP_GROUP_ID")
```

### 3. `Services/whatsapp_service.py`
`send_whatsapp_group_message(group_id, message)` fonksiyonu ekle. Mevcut `send_whatsapp_message` ile aynı endpoint/headers, tek fark payload:
```python
payload = {
    "messaging_product": "whatsapp",
    "recipient_type": "group",
    "to": group_id,
    "type": "text",
    "text": {"body": message}
}
```
Status ve response'u logla, response'u döndür.
NOT: Grup gönderimi resmî dokümanda `v25.0` ile gösteriliyor. Şimdilik mevcut sürümü (`v23.0`) kullan ama koda bir yorum ekle: "Grup gönderiminde hata olursa API sürümünü v25.0 yap."

### 4. `Services/openai_service.py`
`_create_chat(messages, sender)` fonksiyonuna opsiyonel `tools=None` parametresi ekle:
- `tools` verilmişse `client.chat.completions.create` çağrısına `tools=tools` ve `tool_choice="auto"` ekle.
- `log_usage` davranışı aynı kalsın.
- Dönen mesajdaki `tool_calls` varsa ilkini parse edip dönüş sözlüğüne `"tool_call": {"name": ..., "arguments": <json.loads ile dict>}` olarak ekle; yoksa `"tool_call": None`. `"answer"` alanı `message.content` olsun (tool çağrısında None olabilir).

`product_chat`, `_create_chat`'i `tools=[SIPARIS_TOOL]` ile çağırsın. `from Services.order_service import SIPARIS_TOOL` import et.

### 5. `main.py`
Importları güncelle: `send_whatsapp_group_message`'ı whatsapp_service'ten, `format_order_message`'ı order_service'ten, `WHATSAPP_GROUP_ID`'yi config'ten ekle.

Ürün akışındaki `product_chat(...)` çağrısından sonra:
- Dönüşteki `tool_call`'a bak. `name == "siparis_olustur"` ise:
  - `arguments`'ı al, `format_order_message` ile mesajı oluştur.
  - `WHATSAPP_GROUP_ID` doluysa `send_whatsapp_group_message` ile gruba gönder; boşsa çökme, sadece logla ("⚠️ WHATSAPP_GROUP_ID tanımlı değil").
  - Grup gönderimini try/except içine al; hata olursa logla ama akışı kesme.
  - Müşteriye dönecek `assistant_answer`: "Siparişiniz alındı 😊 En kısa sürede hazırlanıp kargoya verilecek. Kargo takip numaranız mesaj olarak tarafınıza iletilecek 💕"
- Aksi halde `assistant_answer = response["answer"]` (None gelirse nazik bir fallback mesajı kullan).
- Sonra mevcut mantıkla history'ye user + assistant mesajını ekle ve `send_whatsapp_message` ile müşteriye gönder.

### 6. `sales_prompt.txt`
Dosyanın sonuna şu bölümleri ekle:
```
SİPARİŞ ALMA:
Müşteri sipariş vermek isterse şu bilgileri doğal bir şekilde topla: ad soyad, telefon, açık teslimat adresi, ürün + renk + beden + adet, ödeme şekli.
Eksik bilgi varsa nazikçe sor. Hepsi tamamlanınca siparişi madde madde özetle ve "Onaylıyor musunuz?" diye sor.
Müşteri açıkça onaylarsa (evet/onaylıyorum), siparis_olustur fonksiyonunu çağır. Onaydan önce ASLA çağırma. Sipariş bilgisi uydurma.

ÖDEME SEÇENEKLERİ:
- Kapıda Ödeme (nakit veya kart): 90 TL ek ücret alınır.
- Havale/EFT: IBAN TR12 3456 7890 1234 5678 9012 34 (TEST), NilNur Moda. Müşteri havale seçerse bu IBAN'ı paylaş.

KARGO BİLGİSİ:
- MNG ve DHL ile çalışıyoruz; ortalama teslimat 1-3 iş günü.
- Şeffaf kargo: paketiniz şeffaf şekilde tarafınıza ulaşır.
- Adresiniz köy veya şehir merkezine uzaksa PTT ile gönderilir; lütfen belirtin.
- Kargo takip numarası mesaj olarak iletilir.
```

---

## Kısıtlar
- Mevcut ürün sohbeti, genel sohbet, sesli mesaj ve dashboard akışlarını **bozma**.
- Onaydan önce sipariş gruba **gitmesin**.
- `WHATSAPP_GROUP_ID` boşken uygulama **çökmesin** (sipariş alınır, grup adımı atlanır, log uyarısı verilir).
- Token/maliyet loglaması (`log_usage`) aynen çalışmaya devam etsin.
- Mevcut kod stiline uy: Türkçe yorumlar, raw yapı, fonksiyon imzalarını koru.
- Yeni bağımlılık ekleme.

## Kabul kriterleri
1. Müşteri ürün linki gönderip sipariş vermek isteyince bot eksik alanları tek tek sorar, hepsi tamamlanınca özet + "Onaylıyor musunuz?" der.
2. Müşteri onaylayınca: gruba `format_order_message` formatında mesaj gider VE müşteriye onay/kargo bilgilendirmesi döner.
3. `WHATSAPP_GROUP_ID` tanımsızken sipariş yine alınır, grup adımı atlanır, uygulama çökmez.
4. Onay verilmeden tool çağrılmaz; yanlış/erken sipariş gruba gitmez.

## Teslimden önce
Değişikliklerin özetini ve `.env`'e eklemem gereken `WHATSAPP_GROUP_ID` satırını bana ver. Test için izlenecek adımları da yaz.
