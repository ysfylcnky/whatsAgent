"""Panel (dashboard) kimlik doğrulaması — JWT tabanlı oturum yönetimi.

Panel önceden HTTP Basic Auth ile korunuyordu: parola her istekte tekrar
gönderiliyor, çıkış (logout) yapılamıyor ve oturum süresi tanımlanamıyordu.
Bu modül bunun yerine kısa ömürlü, imzalı bir JWT'yi httpOnly çerezde taşıyan
bir oturum katmanı sağlar.

Neden httpOnly çerez?
    Panel sunucu tarafında (Jinja2 SSR) render edilen HTML sayfalarından oluşur.
    Token'ı JavaScript'in erişemediği bir httpOnly çerezde tutmak, tarayıcının
    her istekte otomatik göndermesini sağlar ve XSS ile token çalınmasını
    engeller. (Bearer header yaklaşımı React/mobil istemciler içindir.)

Parola saklama:
    Parola asla düz metin karşılaştırılmaz. bcrypt hash'i doğrulanır. Hash
    .env'deki DASHBOARD_PASSWORD_HASH'ten okunur; geçiş kolaylığı için yalnız
    düz metin DASHBOARD_PASSWORD tanımlıysa açılışta ondan türetilir (uyarı
    loglanarak).

Bu modül AI/prompt akışına dokunmaz; yalnız panel erişimini yönetir.
"""

import time

import bcrypt
import jwt

from config import (
    JWT_SECRET,
    JWT_EXPIRE_HOURS,
    JWT_ALGORITHM,
    DASHBOARD_USER,
    DASHBOARD_PASSWORD,
    DASHBOARD_PASSWORD_HASH,
)

# Çerez adı tek noktada tanımlıdır (DRY); set/clear/read hepsi bunu kullanır.
COOKIE_NAME = "wa_session"

# bcrypt tek seferde en fazla 72 bayt işler; daha uzun parolalar sessizce
# kırpılır. Bunu önlemek için parola önce sabit uzunlukta güvenli bir ön-özete
# indirgenmez — bunun yerine 72 bayt sınırı korunur ve doğrulama simetrik kalır.
_BCRYPT_MAX_BYTES = 72


def _to_bcrypt_bytes(password):
    """Parolayı bcrypt'in beklediği bayt dizisine çevirir (72 bayt sınırı)."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password):
    """Düz metin paroladan bcrypt hash üretir (kurulum/araç amaçlı)."""
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


# ----------------------------------------------------------------------
# Etkin parola hash'i — açılışta bir kez çözümlenir
# ----------------------------------------------------------------------

def _resolve_password_hash():
    """Kullanılacak bcrypt hash'ini döndürür; yoksa None (panel kapalı).

    Öncelik DASHBOARD_PASSWORD_HASH'tir. O yoksa, geçiş kolaylığı için düz
    metin DASHBOARD_PASSWORD'den türetilir ve düz metin kullanımı için uyarı
    basılır. İkisi de yoksa panel fail-closed olur.
    """
    if DASHBOARD_PASSWORD_HASH:
        return DASHBOARD_PASSWORD_HASH.encode("utf-8")

    if DASHBOARD_PASSWORD:
        print(
            "⚠️ DASHBOARD_PASSWORD_HASH tanımlı değil — düz metin "
            "DASHBOARD_PASSWORD'den geçici hash türetildi. Güvenlik için "
            "generate_password_hash.py ile hash üretip .env'e "
            "DASHBOARD_PASSWORD_HASH olarak koyun."
        )
        return bcrypt.hashpw(_to_bcrypt_bytes(DASHBOARD_PASSWORD), bcrypt.gensalt())

    print(
        "⛔ Ne DASHBOARD_PASSWORD_HASH ne DASHBOARD_PASSWORD tanımlı — "
        "panel girişi kapalı (fail-closed)."
    )
    return None


_PASSWORD_HASH = _resolve_password_hash()


# ----------------------------------------------------------------------
# Kimlik doğrulama
# ----------------------------------------------------------------------

def verify_credentials(username, password):
    """Kullanıcı adı + parolayı doğrular. Başarılıysa True.

    Parola hash tanımlı değilse her zaman False (panel kapalı). Kullanıcı adı
    yanlış olsa bile bcrypt karşılaştırması yapılır; böylece "kullanıcı var mı"
    bilgisini yanıt süresinden sızdıran zamanlama farkı oluşmaz.
    """
    candidate = _to_bcrypt_bytes(password or "")

    if _PASSWORD_HASH is None:
        # Sabit süreli sahte doğrulama: erken dönüşten kaynaklı zamanlama sızıntısı olmasın.
        bcrypt.checkpw(candidate, bcrypt.hashpw(b"x", bcrypt.gensalt()))
        return False

    user_ok = _constant_time_eq(username or "", DASHBOARD_USER or "")
    pass_ok = bcrypt.checkpw(candidate, _PASSWORD_HASH)

    return user_ok and pass_ok


def _constant_time_eq(a, b):
    """Sabit süreli string karşılaştırması (hmac.compare_digest sarmalayıcı)."""
    import hmac
    return hmac.compare_digest(a, b)


# ----------------------------------------------------------------------
# Token üretimi / doğrulaması
# ----------------------------------------------------------------------

def create_token(username):
    """Verilen kullanıcı için imzalı, süreli bir JWT üretir."""
    now = int(time.time())

    payload = {
        "sub": username,
        "iat": now,
        "exp": now + JWT_EXPIRE_HOURS * 3600,
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token):
    """Token'ı doğrular; geçerliyse kullanıcı adını, değilse None döndürür.

    İmza, son kullanma (exp) ve biçim hataları burada yakalanır; süresi dolmuş
    veya kurcalanmış token sessizce reddedilir.
    """
    if not token:
        return None

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    return payload.get("sub")


def is_auth_configured():
    """Panel girişi yapılandırılmış mı (parola hash + JWT secret var mı)."""
    return _PASSWORD_HASH is not None and bool(JWT_SECRET)
