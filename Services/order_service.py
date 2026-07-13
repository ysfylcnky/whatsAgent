from datetime import datetime
from Services.usage_logger import get_connection

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


def build_order_block(order):
    """Mevcut (oluşturulmuş) siparişi modele bağlam olarak vermek için metin üretir.

    Güncelleme akışında model, değişmeyen alanları bu bloktaki mevcut değerlerden
    okur; böylece tüm siparişi baştan sormaz ve eksik alanları null bırakmaz.
    Sipariş yoksa boş metin döner (bağlam eklenmez).
    """
    if not order:
        return ""

    return (
        f"Ad Soyad: {order.get('ad_soyad', '')}\n"
        f"Telefon: {order.get('telefon', '')}\n"
        f"Adres: {order.get('teslimat_adresi', '')}\n"
        f"Ürün: {order.get('urun', '')}\n"
        f"Renk: {order.get('renk', '')}\n"
        f"Beden: {order.get('beden', '')}\n"
        f"Adet: {order.get('adet', '')}\n"
        f"Ödeme: {order.get('odeme_sekli', '')}"
    )


# Modelin güncellemede boş/eksik gönderdiği alanları temsil eden değerler.
# Bu değerler "değişmedi" kabul edilip önceki siparişin değeri korunur.
_EMPTY_ORDER_VALUES = {None, "", "bilgi yok", "Bilgi yok", "BİLGİ YOK"}


def merge_order(previous, updated):
    """Güncelleme aracının argümanlarını önceki sipariş üstüne bindirir.

    Model yalnızca değişen alanı güvenilir doldurabildiğinden, boş/eksik gönderilen
    alanlar için önceki siparişin değeri korunur (null/0 kaydı önlenir). previous
    yoksa updated aynen döner (davranış bozulmaz).
    """
    if not previous:
        return updated

    merged = dict(previous)

    for key, value in (updated or {}).items():

        if value in _EMPTY_ORDER_VALUES:
            continue

        # Adet: model 0/None gönderdiyse "değişmedi" say, önceki adedi koru
        if key == "adet":
            try:
                if int(value) <= 0:
                    continue
            except (TypeError, ValueError):
                continue

        merged[key] = value

    return merged


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


def save_order(customer_phone, order, is_update=False):
    """Sipariş bilgisini kalıcı olarak customers + orders tablolarına yazar.

    customer_phone: WhatsApp gönderen numarası (müşteri anahtarı; siparişteki
    'telefon' alanından farklı olabilir). is_update=True ise güncelleme yeni bir
    orders satırı olarak eklenir (geçmiş korunur).

    Yazma hatası sipariş/notify/yanıt akışını KESMEZ; tüm hatalar yutulur.
    """
    conn = None

    try:

        conn = get_connection()

        cursor = conn.cursor()

        now = datetime.now()

        # Müşteri kaydı: yoksa oluştur, varsa ad_soyad/last_seen tazele
        cursor.execute(
            """
            INSERT INTO customers (phone, ad_soyad, first_seen, last_seen)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                ad_soyad = VALUES(ad_soyad),
                last_seen = VALUES(last_seen)
            """,
            (
                customer_phone,
                order.get("ad_soyad", ""),
                now,
                now
            )
        )

        # Sipariş satırı (güncelleme de yeni satır olarak eklenir: is_update)
        cursor.execute(
            """
            INSERT INTO orders (
                timestamp,
                customer_phone,
                ad_soyad,
                telefon,
                teslimat_adresi,
                urun,
                renk,
                beden,
                adet,
                odeme_sekli,
                is_update
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                now,
                customer_phone,
                order.get("ad_soyad", ""),
                order.get("telefon", ""),
                order.get("teslimat_adresi", ""),
                order.get("urun", ""),
                order.get("renk", ""),
                order.get("beden", ""),
                order.get("adet") or 0,
                order.get("odeme_sekli", ""),
                1 if is_update else 0
            )
        )

        conn.commit()
        cursor.close()

    except Exception as e:

        print("🔴 save_order hatası:", e)

    finally:

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
