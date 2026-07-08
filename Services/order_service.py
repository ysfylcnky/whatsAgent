from datetime import datetime

# OpenAI tool tanımı.
# Model bu fonksiyonu YALNIZCA müşteri özeti açıkça onayladıktan ve
# tüm alanlar tamamlandıktan sonra çağırır. Onaydan önce ASLA çağrılmaz.
SIPARIS_TOOL = {
    "type": "function",
    "function": {
        "name": "siparis_olustur",
        "description": (
            "Müşteri sipariş özetini AÇIKÇA onayladıktan sonra, tüm alanlar "
            "tamamlanınca çağrılır; onaydan önce ASLA çağırma. Sipariş bilgisi "
            "uydurma, sadece müşteriden alınan bilgileri kullan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ad_soyad": {
                    "type": "string",
                    "description": "Müşterinin adı ve soyadı"
                },
                "telefon": {
                    "type": "string",
                    "description": "Müşterinin telefon numarası"
                },
                "teslimat_adresi": {
                    "type": "string",
                    "description": "Açık teslimat adresi"
                },
                "urun": {
                    "type": "string",
                    "description": "Sipariş edilen ürün"
                },
                "renk": {
                    "type": "string",
                    "description": "Ürün rengi"
                },
                "beden": {
                    "type": "string",
                    "description": "Ürün bedeni"
                },
                "adet": {
                    "type": "integer",
                    "description": "Sipariş adedi"
                },
                "odeme_sekli": {
                    "type": "string",
                    "enum": ["Kapıda Ödeme", "Havale/EFT"],
                    "description": "Ödeme şekli"
                }
            },
            "required": [
                "ad_soyad",
                "telefon",
                "teslimat_adresi",
                "urun",
                "renk",
                "beden",
                "adet",
                "odeme_sekli"
            ]
        }
    }
}


# Zaten oluşturulmuş (onaylanmış) bir siparişte müşteri değişiklik istediğinde
# çağrılan güncelleme tool'u. Parametreleri siparis_olustur ile aynıdır: mağazaya
# tam ve güncel sipariş iletilebilmesi için tüm alanlar zorunludur (değişmeyenler de
# mevcut değeriyle doldurulur). Ne zaman/nasıl tetikleneceği prompt dosyasında tanımlıdır.
SIPARIS_GUNCELLE_TOOL = {
    "type": "function",
    "function": {
        "name": "siparis_guncelle",
        "description": (
            "Zaten oluşturulmuş (onaylanmış) bir siparişte müşteri değişiklik "
            "istediğinde çağrılır (adres, ürün, renk, beden, adet veya ödeme şekli). "
            "Değişikliği müşteriyle netleştirip onayını aldıktan sonra çağır. "
            "Siparişin GÜNCEL halini eksiksiz gönder: değişen alanların yeni değerini, "
            "değişmeyen alanların mevcut değerini birlikte ilet. Bilgi uydurma."
        ),
        "parameters": SIPARIS_TOOL["function"]["parameters"]
    }
}


def format_order_message(order, is_update=False):

    # Sipariş zamanı: gün.ay.yıl saat:dakika
    zaman = datetime.now().strftime("%d.%m.%Y %H:%M")

    odeme = order.get("odeme_sekli", "")

    # Kapıda Ödeme seçilmişse ek ücret notu eklenir
    if odeme == "Kapıda Ödeme":
        odeme = odeme + " (+90 TL ek ücret)"

    # Güncelleme bildirimi yeni siparişten ayrılsın diye başlık değişir;
    # mağaza sahibi mesajı yeni sipariş sanmaz.
    baslik = "🔄 *SİPARİŞ GÜNCELLEME*" if is_update else "🛒 *YENİ SİPARİŞ*"

    mesaj = (
        f"{baslik}\n"
        f"🕒 {zaman}\n"
        "\n"
        f"👤 Ad Soyad: {order.get('ad_soyad', '')}\n"
        f"📞 Telefon: {order.get('telefon', '')}\n"
        f"📍 Adres: {order.get('teslimat_adresi', '')}\n"
        "\n"
        f"🛍 Ürün: {order.get('urun', '')}\n"
        f"🎨 Renk: {order.get('renk', '')}\n"
        f"📏 Beden: {order.get('beden', '')}\n"
        f"🔢 Adet: {order.get('adet', '')}\n"
        "\n"
        f"💳 Ödeme: {odeme}\n"
    )

    return mesaj
