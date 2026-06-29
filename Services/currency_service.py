import time
import requests
from config import CURRENCY_CACHE_TTL

currency_cache = {
    "rate": None,
    "updated_at": 0
}

def get_usd_try_rate():

    now = time.time()

    if (
        currency_cache["rate"] is not None
        and now - currency_cache["updated_at"] < CURRENCY_CACHE_TTL
    ):
        print("🟢 Currency Cache HIT")
        return currency_cache["rate"]

    print("🟡 Currency Cache MISS")

    try:

        response = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=5
        )

        response.raise_for_status()

        data = response.json()

        rate = data["rates"]["TRY"]

        currency_cache["rate"] = rate
        currency_cache["updated_at"] = now

        return rate

    except Exception as e:

        print("Currency API Error:", e)

        if currency_cache["rate"] is not None:
            print("🟠 Using cached exchange rate")
            return currency_cache["rate"]

        return None