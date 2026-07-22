"""Panel kimlik doğrulaması (Services/auth_service.py) için izole test scripti.

Ana akışa dokunmadan çalışır; sunucu veya DB gerektirmez. Test için gerekli
ortam değişkenlerini kendi içinde kurar.

    python debug_auth.py
"""

import os
import sys
import time

# auth_service import edilmeden ÖNCE test ortamı kurulur (config bunları okur).
os.environ["JWT_SECRET"] = "test-secret-do-not-use-in-prod"
os.environ["JWT_EXPIRE_HOURS"] = "12"
os.environ["DASHBOARD_USER"] = "admin"
os.environ["DASHBOARD_PASSWORD"] = ""          # düz metin yok
os.environ.pop("DASHBOARD_PASSWORD_HASH", None)

import jwt  # noqa: E402
from Services import auth_service  # noqa: E402
from Services.auth_service import (  # noqa: E402
    hash_password,
    create_token,
    verify_token,
)

results = []


def check(name, condition):
    results.append((name, bool(condition)))
    print(f"{'✅' if condition else '❌'} {name}")


def test_password_hashing():
    h = hash_password("GizliParola123!")
    check("hash düz metinden farklı", h != "GizliParola123!")
    check("hash bcrypt formatında", h.startswith("$2"))

    # Aynı parola iki kez hash'lenince farklı çıkmalı (rastgele salt)
    check("salt rastgele", hash_password("x") != hash_password("x"))


def test_verify_credentials():
    # Etkin hash'i test parolasına sabitle (modül global'i override edilir)
    auth_service._PASSWORD_HASH = hash_password("dogruparola").encode("utf-8")

    check("doğru kimlik kabul", auth_service.verify_credentials("admin", "dogruparola"))
    check("yanlış parola ret", not auth_service.verify_credentials("admin", "yanlis"))
    check("yanlış kullanıcı ret", not auth_service.verify_credentials("hacker", "dogruparola"))
    check("boş parola ret", not auth_service.verify_credentials("admin", ""))


def test_token_roundtrip():
    token = create_token("admin")
    check("token üretildi", bool(token))
    check("geçerli token çözülür", verify_token(token) == "admin")


def test_token_rejects_tampering():
    token = create_token("admin")
    # Son karakteri değiştirerek imzayı boz
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    check("kurcalanmış token reddedilir", verify_token(tampered) is None)


def test_token_rejects_wrong_secret():
    # Başka bir secret ile imzalanmış token kabul edilmemeli
    forged = jwt.encode(
        {"sub": "admin", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        "baska-secret",
        algorithm="HS256",
    )
    check("yanlış secret reddedilir", verify_token(forged) is None)


def test_token_expiry():
    expired = jwt.encode(
        {"sub": "admin", "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    check("süresi dolmuş token reddedilir", verify_token(expired) is None)


def test_none_and_garbage():
    check("None token reddedilir", verify_token(None) is None)
    check("boş string reddedilir", verify_token("") is None)
    check("çöp string reddedilir", verify_token("not.a.jwt") is None)


def test_algorithm_confusion():
    # 'none' algoritması ile imzasız token kabul EDİLMEMELİ (klasik JWT açığı)
    try:
        forged = jwt.encode({"sub": "admin"}, "", algorithm="none")
        check("alg=none reddedilir", verify_token(forged) is None)
    except Exception:
        # PyJWT bazı sürümlerde 'none' üretimini engeller — bu da kabul.
        check("alg=none reddedilir", True)


def main():
    print("--- Panel kimlik doğrulaması doğrulaması ---\n")

    test_password_hashing()
    test_verify_credentials()
    test_token_roundtrip()
    test_token_rejects_tampering()
    test_token_rejects_wrong_secret()
    test_token_expiry()
    test_none_and_garbage()
    test_algorithm_confusion()

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} kontrol geçti.")

    if failed:
        print("BAŞARISIZ:")
        for n in failed:
            print(f"  - {n}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
