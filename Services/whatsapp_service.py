import requests
from config import (
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID
)

def send_whatsapp_message(to_number, message):

    url = (
        f"https://graph.facebook.com/v23.0/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization":
            f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": message
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload
    )

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)


def send_whatsapp_group_message(group_id, message):

    # Grup gönderiminde hata olursa API sürümünü v25.0 yap.
    url = (
        f"https://graph.facebook.com/v23.0/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization":
            f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "group",
        "to": group_id,
        "type": "text",
        "text": {
            "body": message
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload
    )

    print("GROUP STATUS:", response.status_code)
    print("GROUP RESPONSE:", response.text)

    return response
