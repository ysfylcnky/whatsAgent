"""Panel kullanıcıları (users tablosu) için ORM veri erişimi.

Faz 2: e-posta/şifre kimlik doğrulaması artık `users` tablosundan yapılır.
Bu modül YALNIZ veri katmanıdır — kripto (bcrypt) burada değildir; parola
hash'i çağıran tarafça (auth_service.hash_password) üretilip `password_hash`
olarak verilir. Böylece auth_service <-> user_service arasında import döngüsü
oluşmaz.

DB erişilemezse okuma fonksiyonları uygulamayı çökertmez; None / 0 döner
(auth_service bu durumda .env fallback'ine düşebilir).
"""

from datetime import datetime

from sqlalchemy import select, func

from Services.db import get_session
from Services.models import User


def _to_dict(user):
    """User ORM nesnesini oturumdan bağımsız düz dict'e çevirir."""
    if user is None:
        return None
    return {
        "id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": user.role,
    }


def get_user_by_email(email):
    """E-postaya göre tek kullanıcıyı döndürür (yoksa/erişilemezse None).

    Dönen değer oturum kapandıktan sonra da kullanılabilsin diye düz dict'tir.
    """
    if not email:
        return None
    try:
        with get_session() as session:
            user = session.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            return _to_dict(user)
    except Exception as e:
        print("🔴 get_user_by_email hatası:", e)
        return None


def create_user(tenant_id, email, password_hash, role="owner"):
    """Verilen tenant'a yeni panel kullanıcısı ekler (ORM).

    password_hash zaten bcrypt ile üretilmiş olmalıdır (düz metin DEĞİL).
    Aynı e-posta zaten varsa yeni kayıt açmaz, mevcut kullanıcıyı döndürür
    (idempotent seed/çağrı için). Başarısızlıkta None döner.
    """
    if not email or not password_hash:
        return None
    try:
        existing = get_user_by_email(email)
        if existing is not None:
            return existing

        with get_session() as session:
            user = User(
                tenant_id=tenant_id,
                email=email,
                password_hash=password_hash,
                role=role,
                created_at=datetime.now(),
            )
            session.add(user)
            session.flush()  # id'yi almak için commit öncesi flush
            return _to_dict(user)
    except Exception as e:
        print("🔴 create_user hatası:", e)
        return None


def count_users():
    """Toplam kullanıcı sayısı (erişilemezse 0)."""
    try:
        with get_session() as session:
            return int(session.execute(select(func.count(User.id))).scalar() or 0)
    except Exception as e:
        print("🔴 count_users hatası:", e)
        return 0
