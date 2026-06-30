import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-4.1-mini"
AUDIO_MODEL_NAME = "gpt-4o-mini-transcribe"

# WhatsApp
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_GROUP_ID = os.getenv("WHATSAPP_GROUP_ID")

# MySQL (bağlantı bilgileri .env'den okunur)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

# App
CACHE_TTL = 600
MAX_HISTORY = 20
MAX_PRODUCTS = 5
SESSION_TIMEOUT = 60 * 30
PROCESSED_MESSAGE_TTL = 600

VERIFY_TOKEN = "mumi_verify_token"

# GPT-4.1-mini Pricing (USD / 1M Tokens)

INPUT_TOKEN_PRICE = 0.40

OUTPUT_TOKEN_PRICE = 1.60

CURRENCY_CACHE_TTL = 3600

AVERAGE_CHAT_TIME_MINUTES = 4
EMPLOYEE_HOURLY_COST = 250
