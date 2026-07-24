"""migrate_faz2_admin_user.py — Mumi panel kullanıcısını users tablosuna seed eder.

Faz 2: kimlik doğrulama artık `users` tablosundan yapılıyor. Bu script, bugüne
dek .env ile giren Mumi admin'ini users tablosuna (tenant_id=1) taşır ki DB
tabanlı giriş sorunsuz çalışsın. .env fallback'i authenticate içinde kalsa da
asıl yol budur.

TAMAMEN ADDITIVE ve IDEMPOTENT: aynı e-posta zaten varsa yeni kayıt açmaz.
Şema değişmez (yalnız veri eklenir); yine de deploy'da yedekle çalışmak iyidir.

Parola kaynağı (öncelik sırası):
  1. DASHBOARD_PASSWORD_HASH (bcrypt) — doğrudan kullanılır.
  2. DASHBOARD_PASSWORD (düz metin) — bcrypt ile hash'lenir.
  3. İkisi de yoksa seed yapılamaz (uyarı basılır).

Canlı çalıştırma (Docker):
    docker compose exec app python migrate_faz2_admin_user.py
"""

from config import (
    DASHBOARD_USER,
    DASHBOARD_PASSWORD,
    DASHBOARD_PASSWORD_HASH,
)
from Services.auth_service import hash_password
from Services.user_service import get_user_by_email, create_user

# Mumi, Faz 1 seed'inde tenant_id=1 olarak tanımlıdır.
MUMI_TENANT_ID = 1


def _resolve_password_hash():
    """Seed için kullanılacak bcrypt hash'ini döndürür (yoksa None)."""
    if DASHBOARD_PASSWORD_HASH:
        return DASHBOARD_PASSWORD_HASH
    if DASHBOARD_PASSWORD:
        print("  ! DASHBOARD_PASSWORD_HASH yok; düz metin DASHBOARD_PASSWORD'den hash türetiliyor.")
        return hash_password(DASHBOARD_PASSWORD)
    return None


def run_seed():
    """Mumi admin kullanıcısını idempotent olarak ekler. Başarıda True."""
    email = DASHBOARD_USER

    if not email:
        print("  XX DASHBOARD_USER tanımlı değil — seed yapılamıyor.")
        return False

    existing = get_user_by_email(email)
    if existing is not None:
        print(f"  = users: '{email}' zaten var (id={existing['id']}, tenant={existing['tenant_id']}), dokunulmadi")
        return True

    pw_hash = _resolve_password_hash()
    if not pw_hash:
        print("  XX Ne DASHBOARD_PASSWORD_HASH ne DASHBOARD_PASSWORD var — seed yapılamıyor.")
        return False

    user = create_user(
        tenant_id=MUMI_TENANT_ID,
        email=email,
        password_hash=pw_hash,
        role="owner",
    )
    if user is None:
        print("  XX create_user başarısız (log'a bak).")
        return False

    print(f"  + users: '{email}' eklendi (id={user['id']}, tenant={MUMI_TENANT_ID}, role=owner)")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Faz 2 Mumi admin seed — CANLI MySQL")
    print("=" * 60)
    ok = run_seed()
    print("\nSONUC:", "BASARILI" if ok else "EKSIK/HATA (yukariya bak)")
