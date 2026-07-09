"""Kurulum (Setup) servisi — SaaS onboarding'in backend mantığı.

Tasarım kuralı (mimariyi bozmadan, minimum müdahale):
  * Secret / import-time okunan tüm değerler .env'e yazılır (dotenv.set_key);
    uygulanması sunucu yeniden başlatılınca olur. Böylece servis dosyalarının
    içi hiç değişmez (whatsapp/ikas/openai vb. dokunulmaz).
  * Zaten dinamik okunan alanlar (STORE_IBAN, STORE_IBAN_NAME) ve kurulum
    durumu (SETUP_*, *_TESTED_AT) mevcut `settings` tablosuna yazılır
    (settings_service). IBAN değişimi main.py'de reload_system_prompt() ile
    anında geçerli olur.
  * Test fonksiyonları posted (henüz kaydedilmemiş olabilecek) değerlerle
    KENDİ KENDİNE yeterli çalışır; import-time sabitlere / restart'a bağlı
    değildir. Böylece kullanıcı kaydetmeden önce doğrulayabilir.

Yeni bağımlılık eklenmez: python-dotenv ve requests zaten kuruludur.
"""

import os
import re
from datetime import datetime

import requests
from dotenv import set_key, dotenv_values, find_dotenv

from Services.usage_logger import get_connection
from Services.settings_service import (
    get_all_stored_settings,
    save_stored_settings,
)


# --------------------------------------------------------------------------
# .env yolu — çalışma dizininden bulunur; yoksa proje kökündeki .env varsayılır.
# --------------------------------------------------------------------------
def _env_path():
    found = find_dotenv(usecwd=True)
    if found:
        return found
    # Services/ -> proje kökü
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, ".env")


ENV_PATH = _env_path()


def _ensure_env_file():
    """set_key yazmadan önce .env'in var olduğundan emin ol (ilk kurulum)."""
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "a", encoding="utf-8").close()


# --------------------------------------------------------------------------
# Alan şeması — her bölüm ve alanın tipi/zorunluluğu/hedefi.
#   target: "env"     -> .env'e yazılır (restart ile geçerli)
#           "setting" -> settings tablosuna yazılır (anında geçerli olabilir)
#           "readonly"-> gösterilir ama ASLA bu endpoint'ten yazılmaz (ör. MySQL)
# --------------------------------------------------------------------------
SECTIONS = [
    {
        "id": "company", "required": True, "test": False,
        "fields": {
            "STORE_NAME":      {"type": "text", "target": "setting"},
            "STORE_IBAN":      {"type": "iban", "target": "setting"},
            "STORE_IBAN_NAME": {"type": "text", "target": "setting"},
        },
    },
    {
        "id": "whatsapp", "required": True, "test": True,
        "fields": {
            "WHATSAPP_PHONE_NUMBER_ID": {"type": "digits", "required": True, "target": "env"},
            "WHATSAPP_ACCESS_TOKEN":    {"type": "text", "required": True, "secret": True, "target": "env"},
            "VERIFY_TOKEN":             {"type": "token", "required": True, "target": "env"},
        },
    },
    {
        "id": "ai", "required": True, "test": True,
        "fields": {
            "OPENAI_API_KEY": {"type": "text", "required": True, "secret": True, "target": "env"},
            "MODEL_NAME":     {"type": "text", "target": "env"},
        },
    },
    {
        "id": "ikas", "required": True, "test": True,
        "fields": {
            "IKAS_STORE_NAME":   {"type": "slug", "required": True, "target": "env"},
            "IKAS_CLIENT_ID":    {"type": "text", "required": True, "target": "env"},
            "IKAS_CLIENT_SECRET": {"type": "text", "required": True, "secret": True, "target": "env"},
        },
    },
    {
        "id": "product", "required": False, "test": True,
        "fields": {
            "MAX_PRODUCTS": {"type": "number", "target": "env", "min": 1, "max": 10},
            "CACHE_TTL":    {"type": "number", "target": "env", "min": 60, "max": 3600},
        },
    },
    {
        "id": "notify", "required": True, "test": True,
        "fields": {
            "STORE_NOTIFY_PHONE": {"type": "phone", "required": True, "target": "env"},
        },
    },
    {
        "id": "advanced", "required": False, "test": False,
        "fields": {
            "DASHBOARD_USER":     {"type": "text", "target": "env"},
            "DASHBOARD_PASSWORD": {"type": "text", "secret": True, "target": "env", "min_len": 8},
            "MYSQL_HOST":     {"type": "text", "target": "readonly"},
            "MYSQL_PORT":     {"type": "number", "target": "readonly"},
            "MYSQL_USER":     {"type": "text", "target": "readonly"},
            "MYSQL_PASSWORD": {"type": "text", "secret": True, "target": "readonly"},
            "MYSQL_DATABASE": {"type": "text", "target": "readonly"},
        },
    },
]

# Kurulumun "tamamlandı" sayılması için .env'de dolu olması gereken anahtarlar.
# (STORE_NAME gibi kozmetik alanlar tamamlanmayı bloklamaz.)
REQUIRED_ENV_KEYS = [
    "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN", "VERIFY_TOKEN",
    "OPENAI_API_KEY",
    "IKAS_STORE_NAME", "IKAS_CLIENT_ID", "IKAS_CLIENT_SECRET",
    "STORE_NOTIFY_PHONE",
]


def _section(section_id):
    for s in SECTIONS:
        if s["id"] == section_id:
            return s
    return None


# --------------------------------------------------------------------------
# Okuma / durum
# --------------------------------------------------------------------------
def _db_ok():
    conn = None
    try:
        conn = get_connection()
        return True
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _current_value(key, meta, env_vals, stored):
    if meta["target"] == "setting":
        return stored.get(key)
    return env_vals.get(key) or os.getenv(key)


def _section_status(sec, fields_out, tested_at):
    for f in fields_out:
        if f["required"] and not f["set"]:
            return "missing"
    if sec.get("test") and not tested_at:
        return "untested"
    return "ok"


# Tek yönlü mandal: kurulum bir kez tamamlanınca süreç ömrü boyunca True kalır.
# Böylece tamamlanmış panelde her istekte DB'ye gidilmez ve geçici DB kesintisi
# kullanıcıyı Kurulum ekranına düşürmez (kurulum geri alınmaz).
_setup_complete_cache = False


def is_setup_complete(env_vals=None, stored=None, db_ok=None):
    """DB erişilebilir + zorunlu .env anahtarları dolu + SETUP_COMPLETED=1."""
    global _setup_complete_cache
    if _setup_complete_cache:
        return True

    if env_vals is None:
        env_vals = dotenv_values(ENV_PATH)
    if stored is None:
        stored = get_all_stored_settings()
    if db_ok is None:
        db_ok = _db_ok()

    if not db_ok:
        return False
    for k in REQUIRED_ENV_KEYS:
        v = env_vals.get(k) or os.getenv(k)
        if v is None or str(v).strip() == "":
            return False

    complete = str(stored.get("SETUP_COMPLETED", "")).strip() == "1"
    if complete:
        _setup_complete_cache = True
    return complete


def get_setup_state():
    """Tüm bölümlerin alan durumları + statü + genel tamamlanma bilgisi (JSON)."""
    env_vals = dotenv_values(ENV_PATH)
    stored = get_all_stored_settings()
    db_ok = _db_ok()

    sections_out = []
    for sec in SECTIONS:
        fields_out = []
        for key, meta in sec["fields"].items():
            raw = _current_value(key, meta, env_vals, stored)
            is_set = raw is not None and str(raw).strip() != ""
            field = {
                "key": key,
                "type": meta["type"],
                "required": bool(meta.get("required")),
                "secret": bool(meta.get("secret")),
                "target": meta["target"],
                "set": is_set,
                # Secret değerler asla geri gönderilmez; sadece "kayıtlı mı" bilgisi
                "value": None if meta.get("secret") else (raw if is_set else None),
            }
            for extra in ("min", "max", "min_len"):
                if extra in meta:
                    field[extra] = meta[extra]
            fields_out.append(field)

        tested_at = stored.get(sec["id"].upper() + "_TESTED_AT") if sec.get("test") else None
        sections_out.append({
            "id": sec["id"],
            "required": sec["required"],
            "test": bool(sec.get("test")),
            "status": _section_status(sec, fields_out, tested_at),
            "tested_at": tested_at,
            "fields": fields_out,
        })

    return {
        "completed": is_setup_complete(env_vals, stored, db_ok),
        "db_ok": db_ok,
        "sections": sections_out,
    }


# --------------------------------------------------------------------------
# Doğrulama
# --------------------------------------------------------------------------
def _validate(key, meta, value):
    value = "" if value is None else str(value).strip()

    if meta.get("required") and value == "":
        return f"{key} zorunludur."
    if value == "":
        return None  # opsiyonel ve boş — sorun yok

    t = meta["type"]
    if t == "digits" and not re.fullmatch(r"\d{6,25}", value):
        return f"{key} yalnızca rakamlardan oluşmalı."
    if t == "phone" and not re.fullmatch(r"\d{10,15}", value):
        return "Telefon ülke koduyla ve yalnız rakam olmalı (10-15 hane)."
    if t == "slug" and not re.fullmatch(r"[a-z0-9-]+", value):
        return "Mağaza adı yalnız küçük harf, rakam ve tire içerebilir."
    if t == "token" and re.search(r"\s", value):
        return "Verify token boşluk içeremez."
    if t == "iban":
        v = value.replace(" ", "").upper()
        if not re.fullmatch(r"TR\d{24}", v):
            return "IBAN 'TR' + 24 rakamdan oluşmalı."
    if t == "number":
        try:
            n = float(value.replace(",", "."))
        except ValueError:
            return f"{key} sayı olmalı."
        if "min" in meta and n < meta["min"]:
            return f"{key} en az {meta['min']} olmalı."
        if "max" in meta and n > meta["max"]:
            return f"{key} en çok {meta['max']} olmalı."
    if meta.get("min_len") and len(value) < meta["min_len"]:
        return f"{key} en az {meta['min_len']} karakter olmalı."
    return None


# --------------------------------------------------------------------------
# Kaydetme (bölüm bazlı)
# --------------------------------------------------------------------------
def save_section(section_id, fields):
    sec = _section(section_id)
    if not sec:
        return {"ok": False, "error": "Bilinmeyen bölüm."}
    if not isinstance(fields, dict):
        return {"ok": False, "error": "Geçersiz gövde."}

    env_writes = {}
    setting_writes = {}
    restart_required = False

    for key, meta in sec["fields"].items():
        if meta["target"] == "readonly":
            continue  # ör. MySQL — çalışan uygulamanın DB'sini web'den bozmayı engelle
        if key not in fields:
            continue

        raw = fields[key]
        val = "" if raw is None else str(raw).strip()

        # Secret alan boş bırakıldıysa mevcut kayıtlı değer korunur
        if meta.get("secret") and val == "":
            continue

        err = _validate(key, meta, val)
        if err:
            return {"ok": False, "error": err}

        if meta["type"] == "iban" and val != "":
            val = val.replace(" ", "").upper()
        if meta["type"] == "number" and val != "":
            n = float(val.replace(",", "."))
            val = str(int(n)) if n == int(n) else str(n)

        if meta["target"] == "setting":
            setting_writes[key] = val
        else:
            env_writes[key] = val
            restart_required = True

    # Koşullu kural: IBAN girildiyse IBAN adı da olmalı
    if section_id == "company":
        stored = get_all_stored_settings()
        iban = setting_writes.get("STORE_IBAN", stored.get("STORE_IBAN") or "")
        name = setting_writes.get("STORE_IBAN_NAME", stored.get("STORE_IBAN_NAME") or "")
        if str(iban).strip() and not str(name).strip():
            return {"ok": False, "error": "IBAN girildiğinde IBAN Ad Soyad da zorunludur."}

    if setting_writes:
        if not save_stored_settings(setting_writes):
            return {"ok": False, "error": "Ayar kaydedilemedi (DB erişilemiyor olabilir)."}

    if env_writes:
        try:
            _ensure_env_file()
            for k, v in env_writes.items():
                set_key(ENV_PATH, k, v)
        except Exception as e:
            return {"ok": False, "error": f".env yazılamadı: {e}"}

    return {
        "ok": True,
        "restart_required": restart_required,
        "saved": list(setting_writes.keys()) + list(env_writes.keys()),
    }


# --------------------------------------------------------------------------
# Testler (self-contained; posted değer yoksa kayıtlıya düşer)
# --------------------------------------------------------------------------
def _resolve(values, key):
    """Test için değer: önce posted, yoksa .env/settings'teki mevcut değer."""
    v = values.get(key) if isinstance(values, dict) else None
    v = "" if v is None else str(v).strip()
    if v:
        return v
    meta = None
    for s in SECTIONS:
        if key in s["fields"]:
            meta = s["fields"][key]
            break
    if meta and meta["target"] == "setting":
        return str(get_all_stored_settings().get(key) or "")
    return str(dotenv_values(ENV_PATH).get(key) or os.getenv(key) or "")


def _mark_tested(section_id):
    save_stored_settings({
        section_id.upper() + "_TESTED_AT": datetime.now().isoformat(timespec="seconds")
    })


def _send_whatsapp_raw(phone_number_id, token, to, body):
    url = f"https://graph.facebook.com/v23.0/{phone_number_id}/messages"
    return requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}},
        timeout=15,
    )


# --- Hata mesajı yardımcıları: kullanıcı dostu + secret sızdırmaz -----------
def _redact(text, secrets=()):
    """Metindeki API anahtarı/token değerlerini maskeler (gösterim/log güvenliği)."""
    s = str(text)
    for sec in secrets:
        sec = str(sec or "")
        if len(sec) >= 4:
            s = s.replace(sec, "***")
    return s


def _friendly_conn_error(exc):
    """Ağ istisnasını kullanıcı dostu mesaja çevirir. Ham istisna/secret basmaz."""
    if isinstance(exc, requests.exceptions.Timeout):
        return "Zaman aşımı — sunucu yanıt vermedi. Bilgileri ve bağlantıyı kontrol edin."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Bağlantı kurulamadı — adres/mağaza adını ve internet bağlantısını kontrol edin."
    return "Bağlantı sırasında beklenmeyen bir sorun oluştu. Lütfen tekrar deneyin."


def _http_error_message(r, secrets=()):
    """Sağlayıcı yanıtından güvenli, okunur bir hata mesajı üretir (secret redakte)."""
    msg = None
    try:
        body = r.json()
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
        msg = msg or body.get("error_description") or body.get("message")
    except Exception:
        msg = None
    return _redact(msg or f"HTTP {r.status_code}", secrets)


def _test_whatsapp(values):
    pid = _resolve(values, "WHATSAPP_PHONE_NUMBER_ID")
    token = _resolve(values, "WHATSAPP_ACCESS_TOKEN")
    if not pid or not token:
        return {"ok": False, "error": "Phone Number ID ve Access Token gerekli."}
    try:
        # Token URL'ye değil Authorization başlığına konur — hata/loglarda sızmasın
        r = requests.get(
            f"https://graph.facebook.com/v23.0/{pid}",
            params={"fields": "id,display_phone_number"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception as e:
        return {"ok": False, "error": _friendly_conn_error(e)}
    if r.status_code == 200:
        _mark_tested("whatsapp")
        num = ""
        try:
            num = r.json().get("display_phone_number", "")
        except Exception:
            pass
        return {"ok": True, "message": "WhatsApp bağlantısı doğrulandı" + (f" ({num})" if num else "") + "."}
    if r.status_code in (401, 403):
        return {"ok": False, "error": "Kimlik doğrulanamadı — Access Token geçersiz veya süresi dolmuş olabilir."}
    return {"ok": False, "error": "Doğrulanamadı: " + _http_error_message(r, [token])}


def _test_openai(values):
    key = _resolve(values, "OPENAI_API_KEY")
    if not key:
        return {"ok": False, "error": "OpenAI API anahtarı gerekli."}
    try:
        from openai import OpenAI
        OpenAI(api_key=key).models.list()
    except Exception as e:
        # Ham istisna basılmaz (anahtar sızabilir); tür bazlı dostu mesaj verilir
        name = e.__class__.__name__
        if "Authentication" in name or "Permission" in name:
            return {"ok": False, "error": "API anahtarı geçersiz — OpenAI kimlik doğrulaması başarısız."}
        if "RateLimit" in name:
            return {"ok": False, "error": "OpenAI hız sınırına takıldı; kısa süre sonra tekrar deneyin."}
        if "Connection" in name or "Timeout" in name:
            return {"ok": False, "error": "OpenAI'ye ulaşılamadı — internet bağlantısını kontrol edin."}
        return {"ok": False, "error": "API anahtarı doğrulanamadı. Lütfen kontrol edip tekrar deneyin."}
    _mark_tested("ai")
    return {"ok": True, "message": "OpenAI API anahtarı geçerli."}


def _test_ikas(values):
    store = _resolve(values, "IKAS_STORE_NAME")
    cid = _resolve(values, "IKAS_CLIENT_ID")
    secret = _resolve(values, "IKAS_CLIENT_SECRET")
    if not (store and cid and secret):
        return {"ok": False, "error": "Store Name, Client ID ve Client Secret gerekli."}
    try:
        # client_secret gövdede gönderilir (URL'de değil) — sızıntı riski yok
        r = requests.post(
            f"https://{store}.myikas.com/api/admin/oauth/token",
            data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
    except Exception as e:
        return {"ok": False, "error": _friendly_conn_error(e)}
    try:
        has_token = r.status_code == 200 and bool(r.json().get("access_token"))
    except Exception:
        has_token = False
    if has_token:
        _mark_tested("ikas")
        return {"ok": True, "message": "ikas kimlik doğrulaması başarılı."}
    if r.status_code in (400, 401, 403):
        return {"ok": False, "error": "ikas kimlik doğrulaması başarısız — Client ID/Secret veya Store Name hatalı olabilir."}
    return {"ok": False, "error": "ikas bağlantısı doğrulanamadı: " + _http_error_message(r, [cid, secret])}


def _test_product_search(values):
    query = (values.get("query") if isinstance(values, dict) else None) or "test"
    try:
        from Services.ikas_service import resolve_product_search
        resolve_product_search(str(query).strip())
    except Exception:
        # Ham istisna gösterilmez; ikas kimlik bilgileri dolaylı olarak sızmasın
        return {
            "ok": False,
            "error": "Ürün araması başarısız. Önce ikas bilgilerini kaydedip sunucuyu "
                     "yeniden başlatmayı deneyin.",
        }
    _mark_tested("product")
    return {"ok": True, "message": f"'{query}' için ürün araması çalıştı."}


def _test_notification(values):
    to = _resolve(values, "STORE_NOTIFY_PHONE")
    pid = _resolve(values, "WHATSAPP_PHONE_NUMBER_ID")
    token = _resolve(values, "WHATSAPP_ACCESS_TOKEN")
    if not to:
        return {"ok": False, "error": "Bildirim numarası gerekli."}
    if not (pid and token):
        return {"ok": False, "error": "Önce WhatsApp bilgilerini girin/kaydedin."}
    try:
        r = _send_whatsapp_raw(pid, token, to, "WhatsAgent kurulum testi ✅ — bildirimler bu numaraya gelecek.")
    except Exception as e:
        return {"ok": False, "error": _friendly_conn_error(e)}
    if r.status_code == 200:
        _mark_tested("notify")
        return {"ok": True, "message": "Test bildirimi gönderildi."}
    if r.status_code in (401, 403):
        return {"ok": False, "error": "Kimlik doğrulanamadı — WhatsApp Access Token geçersiz olabilir."}
    return {"ok": False, "error": "Gönderilemedi: " + _http_error_message(r, [token])}


_TESTS = {
    "whatsapp": _test_whatsapp,
    "ai": _test_openai,
    "ikas": _test_ikas,
    "product": _test_product_search,
    "notify": _test_notification,
}


def run_test(section_id, values):
    fn = _TESTS.get(section_id)
    if not fn:
        return {"ok": False, "error": "Bu bölüm için test yok."}
    return fn(values or {})


# --------------------------------------------------------------------------
# Kurulumu tamamla
# --------------------------------------------------------------------------
def mark_complete():
    env_vals = dotenv_values(ENV_PATH)
    stored = get_all_stored_settings()
    if not _db_ok():
        return {"ok": False, "error": "Veritabanına erişilemiyor."}
    missing = [k for k in REQUIRED_ENV_KEYS if not (env_vals.get(k) or os.getenv(k))]
    if missing:
        return {"ok": False, "error": "Eksik zorunlu alanlar: " + ", ".join(missing)}
    ok = save_stored_settings({
        "SETUP_COMPLETED": "1",
        "SETUP_COMPLETED_AT": datetime.now().isoformat(timespec="seconds"),
    })
    if not ok:
        return {"ok": False, "error": "Durum kaydedilemedi (DB)."}
    global _setup_complete_cache
    _setup_complete_cache = True
    return {"ok": True}
