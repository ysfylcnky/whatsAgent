"""
WHATSAPP GRUP KURULUMU: WhatsApp Cloud API Groups API ile "Sipariş Bildirimleri"
adında bir grup oluşturur, ardından grup listesini çekip yeni oluşan grubun
GROUP_ID'sini bulur.

ÖNEMLİ — ERİŞİM KISITI:
WhatsApp Groups API, Meta dokümantasyonuna göre yalnızca "Official Business
Account" (Yeşil Onay Rozeti) sahibi işletme hesaplarında kullanılabilir.
Standart WhatsApp Business hesapları bu API'ye erişemez. Aşağıda "permission"/
"not authorized"/"unsupported request" gibi bir hata alırsanız hesabınız
muhtemelen Official Business Account değildir; Meta Business Suite üzerinden
yeşil rozet başvurusu yapmanız gerekir.

ASENKRON OLUŞTURMA:
Grup oluşturma isteği (POST .../groups) group_id'yi HEMEN döndürmez, yalnızca
bir request_id döner. Bu yüzden bu script oluşturma isteğini attıktan sonra
grup listesini (GET .../groups) birkaç kez kısa aralıklarla kontrol ederek
yeni grubun belirmesini bekler.

Kullanılan API sürümü: v25.0 (grup mesajlaşması/yönetimi bu sürümden itibaren
destekleniyor).

Çalıştır (venv içindeki python ile, proje kökünde):
    python whatsapp_grup_kur.py

Grup zaten oluşturulduysa script'i tekrar çalıştırmak YENİ bir grup daha
oluşturur (aynı isimle). Listede "Sipariş Bildirimleri" adında birden fazla
grup görürseniz en güncel (created_at) olanı kullanın, gereksiz olanları
WhatsApp uygulamasından silin.
"""

import json
import time
import requests
from config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID

API_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}"

GROUP_NAME = "Sipariş Bildirimleri"


def _headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def create_group():

    url = f"{BASE_URL}/groups"

    payload = {
        "messaging_product": "whatsapp",
        "subject": GROUP_NAME,
        "description": "Yeni siparişlerin otomatik olarak iletildiği grup",
        "join_approval_mode": "auto_approve",
    }

    print(f"POST {url}")
    print("Body:", json.dumps(payload, ensure_ascii=False))

    response = requests.post(url, headers=_headers(), json=payload, timeout=30)

    print(f"\n===== GRUP OLUŞTURMA İSTEĞİ (HTTP {response.status_code}) =====")
    print(response.text)

    if response.status_code >= 400:

        print("\n>>> HATA: Grup oluşturulamadı.")
        print(">>> En sık neden: Bu WhatsApp Business hesabı 'Official Business")
        print(">>> Account' (Yeşil Onay Rozeti) değil. Groups API yalnızca Meta")
        print(">>> tarafından onaylı işletme hesaplarında çalışır. Meta Business")
        print(">>> Suite üzerinden yeşil rozet başvurusu yapmanız gerekebilir.")
        print(">>> Ayrıca WHATSAPP_ACCESS_TOKEN'ın 'whatsapp_business_messaging'")
        print(">>> iznine ve doğru işletme hesabına ait olduğundan emin olun.")

        return None

    return response.json()


def list_groups():

    url = f"{BASE_URL}/groups"

    response = requests.get(url, headers=_headers(), timeout=30)

    print(f"\n===== GRUP LİSTESİ (HTTP {response.status_code}) =====")
    print(response.text)

    if response.status_code >= 400:
        return []

    return response.json().get("data", [])


def find_group_by_subject(subject, attempts=5, delay_seconds=3):

    # Grup oluşturma asenkron olduğu için listede belirmesi birkaç saniye sürebilir
    for attempt in range(1, attempts + 1):

        print(f"\nGrup listede aranıyor... (deneme {attempt}/{attempts})")

        groups = list_groups()

        matches = [g for g in groups if g.get("subject") == subject]

        if matches:
            # En güncel oluşturulanı seç (aynı isimle birden fazla grup varsa)
            matches.sort(key=lambda g: g.get("created_at", ""), reverse=True)
            return matches[0]

        if attempt < attempts:
            time.sleep(delay_seconds)

    return None


def main():

    print("Telefon Numarası ID:", WHATSAPP_PHONE_NUMBER_ID)
    print("API sürümü:", API_VERSION)

    created = create_group()

    if created is None:
        return

    print(
        "\nGrup oluşturma isteği kabul edildi (asenkron). request_id:",
        created.get("request_id")
    )

    group = find_group_by_subject(GROUP_NAME)

    if group is None:

        print("\n>>> Grup listede henüz görünmüyor. Birkaç dakika sonra tekrar")
        print(">>> 'python whatsapp_grup_kur.py' çalıştırmayı DENEMEDEN önce")
        print(">>> önce sadece grup listesini kontrol etmek isterseniz bu script'i")
        print(">>> tekrar çalıştırmak yeni bir grup daha oluşturacağı için dikkatli")
        print(">>> olun; grup muhtemelen birazdan oluşacaktır.")

        return

    print("\n" + "=" * 50)
    print("GRUP BULUNDU")
    print("=" * 50)
    print("GROUP_ID:", group.get("id"))
    print("Grup adı:", group.get("subject"))
    print("Oluşturulma zamanı:", group.get("created_at"))

    if group.get("invite_link"):

        print("Davet linki:", group.get("invite_link"))

    else:

        print(
            "Davet linki bu yanıtta yer almıyor (Meta dokümantasyonunda ayrı bir "
            "invite_link alanı bu uç nokta için dokümante edilmemiş). Gruba "
            "katılımcı eklemek için WhatsApp uygulamasından grup ayarlarını "
            "kullanmanız gerekebilir."
        )

    print("\n.env dosyanıza şu satırı ekleyin:")
    print(f"WHATSAPP_GROUP_ID={group.get('id')}")


if __name__ == "__main__":
    main()
