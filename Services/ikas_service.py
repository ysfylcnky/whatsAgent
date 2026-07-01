import requests
import re
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
            "AKTİF ürün olsa da olmasa da geçerlidir: müşteri aktif üründen FARKLI "
            "bir ürün adı söylerse (ör. aktif ürün abaya iken 'trençkot var mı' derse) "
            "bunu reddetme, mutlaka bu aracı çağırıp o ürünü ara. "
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
          selectionType
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
          stockLocationId
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

# searchProducts hiç sonuç döndürmezse (tam metin arama başarısızsa) yedek olarak
# ürünler isimleriyle listelenip Python'da eşlenir.
LIST_PRODUCT_QUERY = """
query ListProduct($pagination: PaginationInput) {
  listProduct(pagination: $pagination) {
    data {
      id
      name
    }
  }
}
"""

_token_cache = {
    "access_token": None,
    "expires_at": 0
}

ikas_search_cache = {}
ikas_product_cache = {}


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


def _meaningful_words(text):

    # Sorgu/ürün adını anlamlı (2+ karakterli) kelimelere ayırır
    norm = _normalize_tr(text)

    return [w for w in re.findall(r"[a-z0-9]+", norm) if len(w) >= 2]


def _word_matches(query_word, name_words):

    # Türkçe ek farklarını tolere etmek için (ör. "desenli" ~ "desen") önek eşleşmesi de kabul edilir
    for name_word in name_words:

        if query_word == name_word:
            return True

        if len(query_word) >= 4 and len(name_word) >= 4:

            shorter, longer = (
                (query_word, name_word)
                if len(query_word) <= len(name_word)
                else (name_word, query_word)
            )

            if longer.startswith(shorter):
                return True

    return False


def _score_match(query_words, name_words):

    if not query_words:
        return 0.0

    matched = sum(1 for w in query_words if _word_matches(w, name_words))

    return matched / len(query_words)


def _search_raw(variables):

    data = _graphql(SEARCH_PRODUCTS_QUERY, variables)

    if not data:
        return []

    return (data.get("searchProducts") or {}).get("results") or []


def _list_product_name_candidates():

    data = _graphql(
        LIST_PRODUCT_QUERY,
        {"pagination": {"page": 1, "limit": 100}}
    )

    if not data:
        return []

    return (data.get("listProduct") or {}).get("data") or []


def get_product_by_id(product_id):

    # Aktif üründe takip sorularında (fiyat/renk/beden) kullanılmak üzere
    # ürünü tam veriyle (varyant/fiyat/stok) id ile yeniden çeker.
    results = _search_raw(
        {
            "input": {
                "productIdList": [product_id],
                "pagination": {"page": 1, "limit": 1}
            }
        }
    )

    return results[0] if results else None


def _get_scored_candidates(name):

    # Sorguya göre skorlanmış (skor, ürün) çiftlerini yüksekten düşüğe sıralı döndürür
    query_words = _meaningful_words(name)

    if not query_words:
        return []

    candidates = _search_raw(
        {
            "input": {
                "query": name,
                "pagination": {"page": 1, "limit": 20}
            }
        }
    )

    if not candidates:
        # Tam metin arama sonuç vermezse ürünler listelenip Python'da eşlenir
        candidates = _list_product_name_candidates()

    if not candidates:
        return []

    scored = []

    for product in candidates:

        name_words = _meaningful_words(product.get("name", ""))
        score = _score_match(query_words, name_words)

        if score > 0:
            scored.append((score, product))

    scored.sort(key=lambda item: item[0], reverse=True)

    return scored


def search_product_by_name(name):

    scored = _get_scored_candidates(name)

    if not scored:
        return None

    best_product = scored[0][1]

    # Aday listProduct'tan (yalnızca id/name) geldiyse ya da varyant verisi eksikse
    # seçilen ürünün tam verisi id ile yeniden çekilir.
    if not best_product.get("variants"):
        return get_product_by_id(best_product.get("id"))

    return best_product


def search_products_ranked(name, limit=5):

    # En fazla `limit` adayı {id, name, score} olarak, yüksekten düşüğe sıralı döndürür
    scored = _get_scored_candidates(name)

    return [
        {
            "id": product.get("id"),
            "name": product.get("name", ""),
            "score": score
        }
        for score, product in scored[:limit]
    ]


# En yüksek skor ikinciden bu kadar (ya da daha fazla) yüksekse "net eşleşme" sayılır
CLEAR_WINNER_MARGIN = 0.25

# Skorlar birbirine yakınsa müşteriye en fazla bu kadar aday sunulur
MAX_SUGGESTIONS = 3


def resolve_product_search(name):

    # Arama sonucunu tek karar noktasında toplar: bulunamadı / net eşleşme / çoklu aday
    ranked = search_products_ranked(name, limit=5)

    if not ranked:
        return {"status": "not_found"}

    if len(ranked) == 1:
        top = ranked[0]
        return {"status": "single", "product_id": top["id"], "name": top["name"]}

    top_score = ranked[0]["score"]
    second_score = ranked[1]["score"]

    if top_score - second_score >= CLEAR_WINNER_MARGIN:
        top = ranked[0]
        return {"status": "single", "product_id": top["id"], "name": top["name"]}

    close_candidates = [
        c for c in ranked
        if top_score - c["score"] <= CLEAR_WINNER_MARGIN
    ][:MAX_SUGGESTIONS]

    if len(close_candidates) == 1:
        top = close_candidates[0]
        return {"status": "single", "product_id": top["id"], "name": top["name"]}

    return {"status": "multiple", "candidates": close_candidates}


def match_candidate_by_text(text, candidates):

    # pending_products listesinden müşterinin mesajına en uygun adayı seçer (yoksa None)
    words = _meaningful_words(text)

    if not words:
        return None

    best = None
    best_score = 0.0

    for candidate in candidates:

        name_words = _meaningful_words(candidate.get("name", ""))
        score = _score_match(words, name_words)

        if score > best_score:
            best_score = score
            best = candidate

    # Belirsiz/zayıf eşleşmeleri (yanlış pozitif) elemek için asgari skor aranır
    if best is None or best_score < 0.5:
        return None

    return best


# selectionType eksik geldiğinde (ya da belirsiz kaldığında) isme düşülür.
# Mağazaya özgü yazımları da (RENKK, BEDENN) kapsar — tip ADINA güvenmek yerine
# yalnızca selectionType yokken son çare olarak kullanılır.
COLOR_TYPE_NAME_HINTS = ("renk", "renkk", "color", "colour")
SIZE_TYPE_NAME_HINTS = ("beden", "bedenn", "size", "numara", "olcu")


def _classify_variant_types(variant_types):

    # Varyant tiplerini isme değil selectionType'a göre ayırır (COLOR/CHOICE).
    # Renk = selectionType == COLOR olan tip. Beden = renk dışındaki tip
    # (öncelik: isim eşleşmesi, sonra tek CHOICE tip, sonra kalan tek tip).
    color_type = None
    other_types = []

    for entry in variant_types:

        variant_type = (entry or {}).get("variantType") or {}
        selection_type = (variant_type.get("selectionType") or "").strip().upper()
        name_norm = _normalize_tr(variant_type.get("name", ""))

        is_color = selection_type == "COLOR" or (
            not selection_type and name_norm in COLOR_TYPE_NAME_HINTS
        )

        if is_color and color_type is None:
            color_type = variant_type
        else:
            other_types.append(variant_type)

    size_type = None

    # 1) İsimden beden tipini yakala (RENKK/BEDENN gibi mağazaya özgü adlar dahil)
    for variant_type in other_types:

        if _normalize_tr(variant_type.get("name", "")) in SIZE_TYPE_NAME_HINTS:
            size_type = variant_type
            break

    if size_type is None:

        choice_types = [
            vt for vt in other_types
            if (vt.get("selectionType") or "").strip().upper() == "CHOICE"
        ]

        if len(choice_types) == 1:
            size_type = choice_types[0]

        elif choice_types:
            size_type = choice_types[0]

        elif len(other_types) == 1:
            # selectionType hiç verilmemişse ve renk dışında tek tip varsa yine beden say
            size_type = other_types[0]

    return color_type, size_type


def build_ikas_ai_context(product):

    variant_types = product.get("productVariantTypes") or []

    color_type, size_type = _classify_variant_types(variant_types)

    color_type_id = color_type.get("id") if color_type else None
    size_type_id = size_type.get("id") if size_type else None

    colors = []
    sizes = []
    value_name_map = {}

    for entry in variant_types:

        variant_type = (entry or {}).get("variantType") or {}
        values = variant_type.get("values") or []

        for value in values:
            value_name_map[value.get("id")] = (value.get("name") or "").strip(".")

        if variant_type.get("id") == color_type_id:
            colors = [(v.get("name") or "").strip(".") for v in values]

        if variant_type.get("id") == size_type_id:
            sizes = [(v.get("name") or "") for v in values]

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

            if vv.get("variantTypeId") == color_type_id:
                color = value_name

            elif vv.get("variantTypeId") == size_type_id:
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


def debug_dump_product(query, by_id=False):

    # GEÇİCİ DEBUG: Bilinen bir ürünü çekip İKAS'tan dönen HAM yapıyı (productVariantTypes,
    # variants) ve düzeltilmiş mapping'i ekrana basar. Renk/beden mapping sorunlarını
    # teşhis etmek içindir; normal akışta kullanılmaz. Bkz. debug_ikas_product.py.
    product = get_product_by_id(query) if by_id else search_product_by_name(query)

    if not product:
        print(f"DEBUG: '{query}' için ürün bulunamadı")
        return None

    import json as _json

    print("DEBUG HAM İKAS ÜRÜN YAPISI:")
    print(_json.dumps(product, ensure_ascii=False, indent=2))

    context = build_ikas_ai_context(product)

    print("DEBUG DÜZELTİLMİŞ MAPPING:")
    print(_json.dumps(context, ensure_ascii=False, indent=2))

    return product, context


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


def get_cached_ikas_context_by_id(product_id):

    # Aktif ürünün session'daki context'ini tazelemek için id ile çalışır;
    # link parser'ına ihtiyaç duymaz (tek kaynak İKAS).
    now = time.time()

    if product_id in ikas_product_cache:

        cached = ikas_product_cache[product_id]

        if now - cached["created_at"] < CACHE_TTL:
            print(f"🟢 IKAS Cache HIT (id): {product_id}")
            return cached["context"]

        del ikas_product_cache[product_id]

    print(f"🟡 IKAS Cache MISS (id): {product_id}")

    try:
        product = get_product_by_id(product_id)
    except Exception as e:
        print("IKAS FETCH BY ID ERROR:", str(e))
        return None

    if product is None:
        return None

    context = build_ikas_ai_context(product)

    ikas_product_cache[product_id] = {
        "context": context,
        "created_at": now
    }

    return context
