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

    NOT (Faz 2): Bu, geçiş dönemi .env fallback'idir. Birincil kimlik
    doğrulama artık authenticate() ile users tablosundan yapılır.
    """
    candidate = _to_bcrypt_bytes(password or "")

    if _PASSWORD_HASH is None:
        # Sabit süreli sahte doğrulama: erken dönüşten kaynaklı zamanlama sızıntısı olmasın.
        bcrypt.checkpw(candidate, bcrypt.hashpw(b"x", bcrypt.gensalt()))
        return False

    user_ok = _constant_time_eq(username or "", DASHBOARD_USER or "")
    pass_ok = bcrypt.checkpw(candidate, _PASSWORD_HASH)

    return user_ok and pass_ok


# Geçiş dönemi .env fallback'i başarılı olduğunda hangi tenant'a bağlanılacağı.
# Eski tek-kiracılı Mumi = tenant_id 1 (Faz 1 seed'i).
LEGACY_FALLBACK_TENANT_ID = 1


def authenticate(identifier, password):
    """E-posta (veya kullanıcı adı) + parolayı users tablosundan doğrular.

    Başarılıysa {id, tenant_id, email, role} dict'i, değilse None döner.

    Faz 2 davranışı:
      * users tablosunda eşleşen kullanıcı varsa: bcrypt ile parola doğrulanır;
        parola yanlışsa giriş REDDEDİLİR (.env fallback'ine düşülmez — gerçek
        bir başarısız giriştir).
      * Eşleşen kullanıcı yoksa: geçiş dönemi .env doğrulaması (verify_credentials)
        denenir; başarılıysa Mumi (tenant 1) olarak giriş yapılır (deprecation
        uyarısı loglanır). Bu, seed henüz çalışmadıysa kilitlenmeyi önler.

    Sabit-süreli: kullanıcı bulunmasa bile bir bcrypt karşılaştırması yapılır;
    "kullanıcı var mı" bilgisi yanıt süresinden sızmaz.
    """
    candidate = _to_bcrypt_bytes(password or "")

    # Lazy import: auth_service <-> user_service import döngüsünü önler.
    from Services.user_service import get_user_by_email

    user = get_user_by_email(identifier)

    if user is not None:
        stored = (user.get("password_hash") or "").encode("utf-8")
        try:
            ok = bool(stored) and bcrypt.checkpw(candidate, stored)
        except ValueError:
            # Bozuk/eksik hash — güvenli tarafta kal.
            ok = False
        if ok:
            return {
                "id": user["id"],
                "tenant_id": user["tenant_id"],
                "email": user["email"],
                "role": user["role"],
            }
        return None

    # Kullanıcı yok: sabit-süreli sahte bcrypt (timing sızıntısı olmasın).
    bcrypt.checkpw(candidate, bcrypt.hashpw(b"x", bcrypt.gensalt()))

    # Geçiş fallback'i: eski .env admin (yalnız Mumi/tenant 1 için anlamlı).
    if verify_credentials(identifier, password):
        print(
            "⚠️ .env fallback ile giriş (deprecated) — bu kullanıcı users "
            "tablosuna taşınmalı (migrate_faz2_admin_user.py)."
        )
        return {
            "id": None,
            "tenant_id": LEGACY_FALLBACK_TENANT_ID,
            "email": identifier,
            "role": "owner",
        }

    return None


def _constant_time_eq(a, b):
    """Sabit süreli string karşılaştırması (hmac.compare_digest sarmalayıcı)."""
    import hmac
    return hmac.compare_digest(a, b)


# ----------------------------------------------------------------------
# Token üretimi / doğrulaması
# ----------------------------------------------------------------------

def create_token(subject, tenant_id=None, user_id=None, role=None):
    """Verilen özne (e-posta/kullanıcı adı) için imzalı, süreli bir JWT üretir.

    Faz 2: tenant_id / user_id / role claim'leri EKLENİR (verilirse). Parametreler
    opsiyonel olduğundan eski `create_token(username)` çağrıları aynen çalışır.
    Bu claim'ler sonraki fazlarda (webhook routing, veri izolasyonu) aktif
    tenant bağlamını taşır.
    """
    now = int(time.time())

    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + JWT_EXPIRE_HOURS * 3600,
    }

    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if user_id is not None:
        payload["user_id"] = user_id
    if role is not None:
        payload["role"] = role

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token):
    """Token'ı doğrular; geçerliyse TÜM payload'ı (dict), değilse None döndürür.

    İmza, son kullanma (exp) ve biçim hataları burada yakalanır; süresi dolmuş
    veya kurcalanmış token sessizce reddedilir. tenant_id/user_id claim'lerine
    erişmek için kullanılır.
    """
    if not token:
        return None

    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def verify_token(token):
    """Token geçerliyse özneyi (sub), değilse None döndürür.

    Geriye uyumluluk için korunur (require_dashboard_auth ve login_page bunu
    kullanır). decode_token üzerinden çalışır.
    """
    payload = decode_token(token)
    return payload.get("sub") if payload else None


def is_auth_configured():
    """Panel girişi yapılandırılmış mı (parola hash + JWT secret var mı)."""
    return _PASSWORD_HASH is not None and bool(JWT_SECRET)
