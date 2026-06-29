import json
from config import (
    MAX_PRODUCTS
)

def store_product(session, url, ai_context):

    products = session["products"]

    products[url] = ai_context

    while len(products) > MAX_PRODUCTS:

        for key in list(products):

            if key != session["active_url"]:

                del products[key]

                break

        else:

            break

def build_products_block(session):

    products = session["products"]
    active_url = session["active_url"]

    lines = []

    active_context = products.get(active_url)

    if active_context:

        lines.append(
            "AKTİF ÜRÜN — "
            + active_context.get("name", "")
            + ": "
            + json.dumps(active_context, ensure_ascii=False)
        )

    others = []

    for url, ctx in products.items():

        if url == active_url:
            continue

        others.append(
            "— "
            + ctx.get("name", "")
            + ": "
            + json.dumps(ctx, ensure_ascii=False)
        )

    if others:

        lines.append("DİĞER ÜRÜNLER:")
        lines.extend(others)

    return "\n".join(lines)
