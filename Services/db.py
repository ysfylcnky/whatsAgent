"""SQLAlchemy veritabanı zemini — ORM'e kademeli geçişin temeli.

Proje bugüne dek ham SQL (`mysql-connector-python` + elle yazılan sorgular)
kullanıyordu. Multi-tenant SaaS'a geçişte her sorguya elle `tenant_id`
filtresi eklemek, tek bir unutulan yerde veri sızıntısı riski demektir. ORM,
bu filtreyi tek merkezden ve otomatik uygulayabilmenin yoludur.

Bu modül yalnız zemini kurar; mevcut ham SQL kodu çalışmaya devam eder.
Servisler tablo tablo bu katmana taşınacaktır (Faz 0). Sürücü olarak yeni bir
paket eklenmez — mevcut `mysql-connector-python` SQLAlchemy sürücüsü olarak
kullanılır (`mysql+mysqlconnector`).

Kullanım:
    from Services.db import get_session
    from Services.models import Conversation

    with get_session() as s:
        s.add(Conversation(...))
        # context çıkışında otomatik commit; hata olursa rollback
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
)

# Tüm ORM modelleri bu Base'den türer (models.py bunu kullanır).
Base = declarative_base()


def _build_url():
    """SQLAlchemy bağlantı URL'i — mevcut MYSQL_* config'ten üretilir."""
    return (
        f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
        "?charset=utf8mb4"
    )


# Engine tek bir kez kurulur. Havuz ayarları production içindir:
# * pool_pre_ping — kopmuş bağlantıyı kullanmadan önce doğrular (MySQL
#   "server has gone away" hatasını önler).
# * pool_recycle — bağlantıları 1 saatte bir tazeler (MySQL wait_timeout).
engine = create_engine(
    _build_url(),
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=5,
    max_overflow=5,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def get_session():
    """Bir işlem (transaction) sınırı sağlayan oturum context'i.

    Başarıyla tamamlanırsa commit, hata olursa rollback yapılır; her durumda
    oturum kapatılır. Böylece çağıran kod işlem yönetimiyle uğraşmaz.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
