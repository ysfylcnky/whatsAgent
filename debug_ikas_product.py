"""
GEÇİCİ DEBUG SCRIPT: Bilinen bir ürünün İKAS'tan dönen HAM yapısını
(productVariantTypes, variants) ve build_ikas_ai_context ile üretilen
düzeltilmiş mapping'i ekrana basar. Renk/beden mapping sorunlarını gerçek
mağaza verisiyle teşhis etmek içindir.

Kullanım (gerçek .env IKAS_* bilgileri dolu olmalı):
    python debug_ikas_product.py "abaya"
    python debug_ikas_product.py "urun-id-buraya" --id
"""
import sys
from Services.ikas_service import debug_dump_product


def main():

    if len(sys.argv) < 2:
        print('Kullanım: python debug_ikas_product.py "ürün adı" [--id]')
        return

    query = sys.argv[1]
    by_id = "--id" in sys.argv[2:]

    debug_dump_product(query, by_id=by_id)


if __name__ == "__main__":
    main()
