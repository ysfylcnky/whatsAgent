import requests
import json
import time
from config import CACHE_TTL
from bs4 import BeautifulSoup

product_cache = {}

def get_product_context(product_url):

    html = requests.get(product_url).text

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    next_data = soup.find(
        "script",
        {"id": "__NEXT_DATA__"}
    )

    data = json.loads(
        next_data.string
    )

    return data["props"]["pageProps"]["pageSpecificData"]
def build_ai_context(product):

    colors = []
    sizes = []

    for variant_type in product["variantTypes"]:

        variant_name = variant_type["variantType"]["name"]

        if variant_name == "RENKK":

            colors = [
                value["name"].strip(".")
                for value in variant_type["variantType"]["values"]
            ]

        elif variant_name == "BEDEN":

            sizes = [
                value["name"]
                for value in variant_type["variantType"]["values"]
            ]

    color_map = {}

    price = None
    discount_price = None

    for variant in product["variants"]:

        color = None
        size = None

        for value in variant["variantValues"]:

            value_name = value["name"].strip(".")

            if value_name in colors:
                color = value_name

            if value_name in sizes:
                size = value_name

        if color not in color_map:
            color_map[color] = {}

        color_map[color][size] = variant.get("stock", 0)

        if price is None:

            if variant.get("prices"):

                price = variant["prices"][0].get("sellPrice")

                discount_price = (
                    variant["prices"][0]
                    .get("discountPrice")
                )

    variants = []

    for color, size_data in color_map.items():

        variants.append({
            "color": color,
            "sizes": size_data
        })

    return {
        "name": product["name"].strip(),
        "price": price,
        "discount_price": discount_price,
        "available_colors": colors,
            "available_sizes": sizes,
        "variants": variants
    }

def get_cached_ai_context(product_url):
    now = time.time()

    if product_url in product_cache:
        cached = product_cache[product_url]

        if now - cached["created_at"] < CACHE_TTL:
            print(f"🟢 Product Cache HIT: {product_url}")
            return cached["context"]

        del product_cache[product_url]

    print(f"🟡 Product Cache MISS: {product_url}")

    product = get_product_context(product_url)
    ai_context = build_ai_context(product)

    product_cache[product_url] = {
        "context": ai_context,
        "created_at": now
    }

    return ai_context