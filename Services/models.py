"""ORM modelleri — mevcut MySQL şemasını birebir yansıtır.

Bu modeller, usage_logger.py'deki `CREATE TABLE` tanımlarıyla aynı yapıyı
tanımlar (aynı tablo adları, sütunlar, tipler, index'ler). Amaç, mevcut
veritabanına dokunmadan ORM katmanını devreye almaktır — modeller var olan
tablolarla eşleşir, yeni tablo yaratmaz.

Multi-tenant (Faz 1) hazırlığı:
    Her tabloya ileride `tenant_id` sütunu eklenecektir. O aşamada buraya
    `tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True)`
    eklenip mevcut veriler tenant_id=1 (Mumi) olarak taşınacaktır. Şimdilik
    modeller tek-kiracılı şemayı yansıtır.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Double,
    Index,
)
from sqlalchemy.dialects.mysql import TINYINT

from Services.db import Base


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
