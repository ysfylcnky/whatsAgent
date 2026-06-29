import io
import requests

from openai import OpenAI

from config import (
    AUDIO_MODEL_NAME,
    OPENAI_API_KEY,
    WHATSAPP_ACCESS_TOKEN
)

client = OpenAI(
    api_key=OPENAI_API_KEY
)

def get_whatsapp_media_url(media_id):

    url = f"https://graph.facebook.com/v23.0/{media_id}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    return response.json()["url"]

def download_whatsapp_media(media_id):

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"
    }

    media_url = get_whatsapp_media_url(media_id)

    response = requests.get(
        media_url,
        headers=headers,
        timeout=30
    )

    if response.status_code == 404:

        media_url = get_whatsapp_media_url(media_id)

        response = requests.get(
            media_url,
            headers=headers,
            timeout=30
        )

    response.raise_for_status()

    return response.content

def transcribe_audio(audio_bytes):

    audio_file = io.BytesIO(audio_bytes)

    audio_file.name = "voice.ogg"

    transcription = client.audio.transcriptions.create(
        model=AUDIO_MODEL_NAME,
        file=audio_file,
        language="tr"
    )

    return transcription.text.strip()
