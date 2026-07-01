"""
İKAS TEŞHİS v2: varyant tipi sözlüğünü + ürün varyantlarını ham haliyle yazdırır.

İKAS'ta ürün, renk/beden isimlerini tutmaz; sadece id referansı tutar.
İsimler + hangi tipin "renk" olduğu (selectionType) ayrı VariantType sözlüğünde.
Bu script ikisini birden çeker.

Çalıştır (venv içindeki python ile, proje kökünde):
    python ikas_urun_debug.py     (ya da dosya adın neyse: python urun_depug.py)

Çıktının TAMAMINI kopyalayıp paylaş.
"""

import json
import requests
from config import IKAS_STORE_NAME, IKAS_CLIENT_ID, IKAS_CLIENT_SECRET

TOKEN_URL = f"https://{IKAS_STORE_NAME}.myikas.com/api/admin/oauth/token"
GRAPHQL_URL = "https://api.myikas.com/api/v1/admin/graphql"

# 1) Varyant tipi sözlüğü: tip id -> isim/selectionType, değer id -> isim
# NOT: listVariantType doğrudan [VariantType!]! dizisi döndürür (listProduct'ın
# aksine "data" sarmalayıcısı YOKTUR) — bkz. ikas.dev/docs/api/admin-api/variant-type
QUERY_TYPES = """
{
  listVariantType {
    id
    name
    selectionType
    values { id name }
  }
}
"""

# 2) Ürünler: varyantlarda fiyat + stok + hangi tip/değer id'sine ait olduğu
QUERY_PRODUCTS = """
{
  listProduct {
    data {
      id
      name
      totalStock
      variants {
        id
        isActive
        sku
        prices { sellPrice discountPrice buyPrice }
        stocks { stockCount stockLocationId }
        variantValueIds { variantTypeId variantValueId }
      }
    }
  }
}
"""


def get_token():
    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": IKAS_CLIENT_ID,
            "client_secret": IKAS_CLIENT_SECRET,
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def run(token, query, label, limit=None):
    r = requests.post(
        GRAPHQL_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"query": query},
        timeout=30,
    )
    print(f"\n===== {label} (HTTP {r.status_code}) =====")
    data = r.json()

    if "errors" in data:
        print(">>> GRAPHQL HATALARI:")
        print(json.dumps(data["errors"], indent=2, ensure_ascii=False))
        return

    inner = next(iter(data.get("data", {}).values()), {})
    rows = inner.get("data", []) if isinstance(inner, dict) else inner
    if limit:
        rows = rows[:limit]
    print(json.dumps(rows, indent=2, ensure_ascii=False))


def main():
    print("Store:", IKAS_STORE_NAME)
    token = get_token()
    print("Token alındı ✅")

    run(token, QUERY_TYPES, "VARYANT TİPLERİ (renk/beden sözlüğü)")
    run(token, QUERY_PRODUCTS, "ÜRÜNLER (ilk 3)", limit=3)


if __name__ == "__main__":
    main()
