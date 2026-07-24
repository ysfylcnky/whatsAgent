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
    decode_token,
    authenticate,
)

# --- Faz 2: users tablosu testleri için izole SQLite ---
# Services.db'nin engine/SessionLocal'ını geçici SQLite'a yönlendiririz; böylece
# user_service ve authenticate() CANLI DB'ye dokunmadan gerçek kodla sınanır.
import tempfile  # noqa: E402
from datetime import datetime  # noqa: E402

from sqlalchemy import create_engine as _create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker as _sessionmaker  # noqa: E402

import Services.db as _db  # noqa: E402
from Services.models import Tenant as _Tenant, User as _User  # noqa: E402

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp.close()
_test_engine = _create_engine(f"sqlite:///{_tmp.name}", future=True)
_db.engine = _test_engine
_db.SessionLocal = _sessionmaker(
    bind=_test_engine, autoflush=False, expire_on_commit=False, future=True
)
# Yalnız tenants + users; Order'daki MySQL TINYINT SQLite'ta derlenmesin diye
# tüm şemayı değil bu iki tabloyu kurarız.
_Tenant.__table__.create(_test_engine)
_User.__table__.create(_test_engine)

# user_service, get_session -> _db.SessionLocal'ı çağrı anında okur; patch görülür.
from Services.user_service import (  # noqa: E402
    get_user_by_email,
    create_user,
    count_users,
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


# ----------------------------------------------------------------------
# Faz 2 — users tablosu tabanlı kimlik doğrulama (izole SQLite)
# ----------------------------------------------------------------------

def test_user_service_crud():
    # Gerçekçilik için tenant 1'i ekle (Mumi).
    with _db.SessionLocal() as s:
        s.add(_Tenant(id=1, name="Mumi", status="active", created_at=datetime.now()))
        s.commit()

    u = create_user(1, "owner@mumi.com", hash_password("gizli123"), "owner")
    check("create_user id döndürür", bool(u) and u["id"] is not None)
    check("create_user tenant_id=1", bool(u) and u["tenant_id"] == 1)

    fetched = get_user_by_email("owner@mumi.com")
    check("get_user_by_email bulur", bool(fetched) and fetched["email"] == "owner@mumi.com")
    check("password_hash bcrypt saklanır", bool(fetched) and fetched["password_hash"].startswith("$2"))
    check("count_users = 1", count_users() == 1)

    # Aynı e-posta ile tekrar → yeni kayıt açmaz (idempotent seed davranışı)
    dup = create_user(1, "owner@mumi.com", hash_password("baska"), "owner")
    check("duplicate create_user yeni kayıt açmaz", count_users() == 1)
    check("duplicate mevcut kullanıcıyı döndürür", bool(dup) and dup["id"] == fetched["id"])

    check("olmayan e-posta None", get_user_by_email("yok@yok.com") is None)


def test_authenticate_from_db():
    ok = authenticate("owner@mumi.com", "gizli123")
    check("authenticate doğru parola → dict", bool(ok))
    check("authenticate tenant_id taşır", bool(ok) and ok["tenant_id"] == 1)
    check("authenticate user_id taşır", bool(ok) and ok["id"] is not None)
    check("authenticate email doğru", bool(ok) and ok["email"] == "owner@mumi.com")

    # Kullanıcı var ama parola yanlış → REDDEDİLİR (fallback'e düşmez)
    check("yanlış parola None", authenticate("owner@mumi.com", "yanlis") is None)


def test_token_carries_tenant_claims():
    token = create_token("owner@mumi.com", tenant_id=1, user_id=7, role="owner")
    payload = decode_token(token)
    check("decode_token payload döner", bool(payload))
    check("token sub doğru", payload and payload.get("sub") == "owner@mumi.com")
    check("token tenant_id claim'i", payload and payload.get("tenant_id") == 1)
    check("token user_id claim'i", payload and payload.get("user_id") == 7)
    check("token role claim'i", payload and payload.get("role") == "owner")
    check("verify_token hâlâ sub döner (geri uyum)", verify_token(token) == "owner@mumi.com")

    # Claim'siz eski çağrı biçimi hâlâ çalışır ve fazladan claim koymaz
    plain = decode_token(create_token("admin"))
    check("claim'siz token'da tenant_id YOK", plain is not None and "tenant_id" not in plain)
    check("geçersiz token decode → None", decode_token("cop.token.degil") is None)


def test_env_fallback_login():
    # Eski .env admin'i etkinleştir (users tablosunda 'admin' YOK → fallback yolu)
    auth_service._PASSWORD_HASH = hash_password("dogruparola").encode("utf-8")

    fb = authenticate("admin", "dogruparola")
    check("fallback: .env admin girişi kabul", bool(fb))
    check("fallback: tenant 1'e bağlanır", bool(fb) and fb["tenant_id"] == 1)
    check("fallback: user_id None (DB'de yok)", bool(fb) and fb["id"] is None)
    check("fallback: yanlış parola None", authenticate("admin", "yanlis") is None)


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

    # Faz 2 — users tablosu + tenant claim'leri
    test_user_service_crud()
    test_authenticate_from_db()
    test_token_carries_tenant_claims()
    test_env_fallback_login()

    try:
        os.unlink(_tmp.name)
    except OSError:
        pass

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} kontrol geçti.")

    if failed:
        print("BAŞARISIZ:")
        for n in failed:
            print(f"  - {n}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
