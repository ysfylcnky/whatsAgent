import requests
import time
from config import (
    IKAS_STORE_NAME,
    IKAS_CLIENT_ID,
    IKAS_CLIENT_SECRET,
    CACHE_TTL
)

IKAS_TOKEN_URL_TEMPLATE = "https://{store}.myikas.com/api/admin/oauth/token"
IKAS_GRAPHQL_URL = "https://api.myikas.com/api/v1/admin/graphql"

# Model, müşteri bir ürünü İSİMLE sorduğunda bu tool'u çağırır (link akışına ek olarak).
URUN_ARA_TOOL = {
    "type": "function",
    "function": {
        "name": "urun_ara",
        "description": (
            "Müşteri bir ürünü İSİMLE sorduğunda/aradığında (link vermeden) çağır. "
            "Ürün fiyat/renk/beden/stok bilgisi gerektiğinde bunu kullan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "urun_ismi": {
                    "type": "string",
                    "description": "Müşterinin bahsettiği ürünün ismi"
                }
            },
            "required": ["urun_ismi"]
        }
    }
}

SEARCH_PRODUCTS_QUERY = """
query SearchProducts($input: SearchInput!) {
  searchProducts(input: $input) {
    results {
      id
      name
      productVariantTypes {
        variantType {
          id
          name
          values {
            id
            name
          }
        }
      }
      variants {
        id
        prices {
          sellPrice
          discountPrice
        }
        stocks {
          stockCount
        }
        variantValues {
          variantTypeId
          variantValueId
        }
      }
    }
  }
}
"""

_token_cache = {
    "access_token": None,
    "expires_at": 0
}

ikas_search_cache = {}


def _get_access_token():

    now = time.time()

    # Token süresi dolmadan (bitişten ~5 dk önce) yenilenir
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 300:
        return _token_cache["access_token"]

    url = IKAS_TOKEN_URL_TEMPLATE.format(store=IKAS_STORE_NAME)

    response = requests.post(
        url,
        data={
            "grant_type": "client_credentials",
            "client_id": IKAS_CLIENT_ID,
            "client_secret": IKAS_CLIENT_SECRET
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )
    response.raise_for_status()

    data = response.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 14400)

    return _token_cache["access_token"]


def _graphql(query, variables=None):

    try:
        token = _get_access_token()
    except Exception as e:
        print("IKAS TOKEN ERROR:", str(e))
        return None

    try:
        response = requests.post(
            IKAS_GRAPHQL_URL,
            json={
                "query": query,
                "variables": variables or {}
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        print("IKAS GRAPHQL ERROR:", str(e))
        return None

    if payload.get("errors"):
        print("IKAS GRAPHQL ERRORS:", payload["errors"])
        return None

    return payload.get("data")


def _normalize_tr(text):

    # Büyük/küçük harf ve Türkçe karakter duyarsız karşılaştırma için sadeleştirir
    if not text:
        return ""

    text = text.replace("İ", "i").replace("I", "ı").lower()

    replacements = {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u"
    }

    for src, dst in replacements.items():
        text = text.replace(src, dst)

    return text.strip()


def _score_match(query_norm, name_norm):

    if not name_norm:
        return 0

    if name_norm == query_norm:
        return 3

    if name_norm.startswith(query_norm):
        return 2

    if query_norm in name_norm:
        return 1

    return 0


def search_product_by_name(name):

    data = _graphql(
        SEARCH_PRODUCTS_QUERY,
        {
            "input": {
                "query": name,
                "pagination": {"page": 1, "limit": 10}
            }
        }
    )

    if not data:
        return None

    results = (data.get("searchProducts") or {}).get("results") or []

    if not results:
        return None

    query_norm = _normalize_tr(name)

    best_product = results[0]
    best_score = -1

    for product in results:

        name_norm = _normalize_tr(product.get("name", ""))
        score = _score_match(query_norm, name_norm)

        if score > best_score:
            best_score = score
            best_product = product

    return best_product


def build_ikas_ai_context(product):

    variant_types = product.get("productVariantTypes") or []

    colors = []
    sizes = []
    color_type_ids = set()
    size_type_ids = set()
    value_name_map = {}

    for entry in variant_types:

        variant_type = (entry or {}).get("variantType") or {}
        type_name_norm = _normalize_tr(variant_type.get("name", ""))
        values = variant_type.get("values") or []

        for value in values:
            value_name_map[value.get("id")] = (value.get("name") or "").strip(".")

        if type_name_norm in ("renk", "color", "colour"):

            colors = [(v.get("name") or "").strip(".") for v in values]
            color_type_ids.add(variant_type.get("id"))

        elif type_name_norm in ("beden", "size", "numara"):

            sizes = [(v.get("name") or "") for v in values]
            size_type_ids.add(variant_type.get("id"))

    color_map = {}

    price = None
    discount_price = None

    for variant in product.get("variants") or []:

        color = None
        size = None

        for vv in variant.get("variantValues") or []:

            value_name = value_name_map.get(vv.get("variantValueId"))

            if value_name is None:
                continue

            if vv.get("variantTypeId") in color_type_ids:
                color = value_name

            elif vv.get("variantTypeId") in size_type_ids:
                size = value_name

        if color not in color_map:
            color_map[color] = {}

        stock_total = sum(
            (s.get("stockCount") or 0)
            for s in (variant.get("stocks") or [])
        )

        color_map[color][size] = stock_total

        if price is None:

            prices = variant.get("prices") or []

            if prices:
                price = prices[0].get("sellPrice")
                discount_price = prices[0].get("discountPrice")

    variants = []

    for color, size_data in color_map.items():

        variants.append({
            "color": color,
            "sizes": size_data
        })

    return {
        "name": (product.get("name") or "").strip(),
        "price": price,
        "discount_price": discount_price,
        "available_colors": colors,
        "available_sizes": sizes,
        "variants": variants
    }


def get_cached_ikas_context(urun_ismi):

    now = time.time()
    key = _normalize_tr(urun_ismi)

    if key in ikas_search_cache:

        cached = ikas_search_cache[key]

        if now - cached["created_at"] < CACHE_TTL:
            print(f"🟢 IKAS Cache HIT: {urun_ismi}")
            return cached["context"], cached["product_id"]

        del ikas_search_cache[key]

    print(f"🟡 IKAS Cache MISS: {urun_ismi}")

    try:
        product = search_product_by_name(urun_ismi)
    except Exception as e:
        print("IKAS SEARCH ERROR:", str(e))
        return None, None

    if product is None:
        return None, None

    context = build_ikas_ai_context(product)
    product_id = product.get("id")

    ikas_search_cache[key] = {
        "context": context,
        "product_id": product_id,
        "created_at": now
    }

    return context, product_id
