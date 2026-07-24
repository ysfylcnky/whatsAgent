"""ORM modelleri — mevcut MySQL şemasını birebir yansıtır.

Bu modeller, usage_logger.py'deki `CREATE TABLE` tanımlarıyla aynı yapıyı
tanımlar (aynı tablo adları, sütunlar, tipler, index'ler). Amaç, mevcut
veritabanına dokunmadan ORM katmanını devreye almaktır — modeller var olan
tablolarla eşleşir, yeni tablo yaratmaz.

Multi-tenant (Faz 1) — UYGULANDI:
    `tenants` ve `users` tabloları eklendi; 5 mevcut tablonun her birine
    `tenant_id` (FK -> tenants.id, index, nullable) sütunu eklendi. Canlı DB'ye
    bu değişiklik `migrate_faz1_tenant.py` ile additive olarak uygulanır ve
    mevcut satırlar tenant_id=1 (Mumi) ile doldurulur. Sütun şimdilik nullable:
    yazma yolları henüz tenant_id set etmez (o davranış sonraki fazlara ait),
    böylece eski kod bozulmadan çalışmaya devam eder.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Double,
    Index,
    ForeignKey,
)
from sqlalchemy.dialects.mysql import TINYINT

from Services.db import Base


class Tenant(Base):
    """Bir müşteri mağazası — multi-tenant izolasyonun kök kaydı (tenants).

    Faz 1'de eklendi. Mevcut tüm veri, migration ile bu tablodaki ilk kayda
    (id=1, "Mumi") bağlanır; sistem tek-kiracılıdan çok-kiracılıya additive
    olarak geçer. status: 'active' | 'suspended' vb. (panel/faturalandırma).
    """

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    status = Column(String(16), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False)


class User(Base):
    """Panel kullanıcısı — bir tenant'a bağlı giriş hesabı (users).

    Faz 1'de tablo tanımlanır; e-posta/şifre ile doğrulama Faz 2'de bu tablodan
    yapılacaktır (bugünkü .env tabanlı tek kullanıcı yerine). email GLOBAL
    benzersizdir: girişte e-postadan tenant_id çözülür. password_hash bcrypt.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="owner")
    created_at = Column(DateTime, nullable=False)


class UsageLog(Base):
    """LLM istek maliyet/performans kaydı (usage_logs)."""

    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    sender = Column(String(32), nullable=False)
    model = Column(String(64), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    cost = Column(Double, nullable=False)
    response_time = Column(Double, nullable=False)
    # Faz 1: multi-tenant izolasyonu. Şimdilik nullable (eski kod set etmez);
    # migration mevcut satırları tenant_id=1 (Mumi) ile doldurur.
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)

    __table_args__ = (
        Index("idx_timestamp", "timestamp"),
        Index("idx_sender", "sender"),
    )


class Conversation(Base):
    """WhatsApp mesaj kaydı — gelen/giden (conversations)."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    sender = Column(String(32), nullable=False)
    direction = Column(String(8), nullable=False)
    content = Column(Text, nullable=True)
    # Faz 1: multi-tenant izolasyonu (bkz. UsageLog.tenant_id).
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)

    __table_args__ = (
        Index("idx_conv_sender", "sender"),
        Index("idx_conv_timestamp", "timestamp"),
    )


class Customer(Base):
    """Sipariş veren müşteri; WhatsApp numarası birincil anahtar (customers)."""

    __tablename__ = "customers"

    phone = Column(String(32), primary_key=True)
    ad_soyad = Column(String(255), nullable=True)
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    # Faz 1: multi-tenant izolasyonu (bkz. UsageLog.tenant_id).
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)


class Order(Base):
    """Sipariş/güncelleme kaydı; güncelleme is_update=1 ile yeni satır (orders)."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    customer_phone = Column(String(32), nullable=False)
    ad_soyad = Column(String(255), nullable=True)
    telefon = Column(String(64), nullable=True)
    teslimat_adresi = Column(Text, nullable=True)
    urun = Column(String(255), nullable=True)
    renk = Column(String(128), nullable=True)
    beden = Column(String(128), nullable=True)
    adet = Column(Integer, nullable=True)
    odeme_sekli = Column(String(64), nullable=True)
    is_update = Column(TINYINT, nullable=False, default=0)
    # Faz 1: multi-tenant izolasyonu (bkz. UsageLog.tenant_id).
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)

    __table_args__ = (
        Index("idx_orders_phone", "customer_phone"),
        Index("idx_orders_timestamp", "timestamp"),
    )


class Setting(Base):
    """Panelden düzenlenebilen anahtar-değer ayarı (settings)."""

    __tablename__ = "settings"

    skey = Column(String(64), primary_key=True)
    svalue = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False)
    # Faz 1: multi-tenant izolasyonu (bkz. UsageLog.tenant_id). PK (skey) Faz 1'de
    # değişmez; tenant başına ayar (composite key) Faz 3'te ele alınacaktır.
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
