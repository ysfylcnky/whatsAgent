"""Panel parolası için bcrypt hash üreten yardımcı araç.

Kullanım:
    python generate_password_hash.py

Parolayı sorar (ekranda görünmez), ürettiği hash'i ekrana basar. Bu değeri
.env dosyasındaki DASHBOARD_PASSWORD_HASH satırına yapıştırın ve düz metin
DASHBOARD_PASSWORD satırını boşaltın. Böylece parola hiçbir yerde düz metin
tutulmaz.

Docker ortamında:
    docker compose exec app python generate_password_hash.py
"""

import getpass
import sys

from Services.auth_service import hash_password


def main():
    pw1 = getpass.getpass("Yeni panel parolası: ")

    if not pw1:
        print("Boş parola kabul edilmez.")
        return 1

    pw2 = getpass.getpass("Parolayı tekrar girin : ")

    if pw1 != pw2:
        print("Parolalar eşleşmedi.")
        return 1

    print()
    print("Aşağıdaki satırı .env dosyanıza ekleyin (tek satır):")
    print()
    print(f"DASHBOARD_PASSWORD_HASH={hash_password(pw1)}")
    print()
    print("Ardından DASHBOARD_PASSWORD satırını boşaltın.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
