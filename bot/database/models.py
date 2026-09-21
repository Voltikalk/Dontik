from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


class User(Base):
    """Модель пользователя Telegram."""
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    fuel_logs: Mapped[List["FuelLog"]] = relationship("FuelLog", back_populates="user", cascade="all, delete-orphan")
    service_logs: Mapped[List["ServiceLog"]] = relationship("ServiceLog", back_populates="user", cascade="all, delete-orphan")
    item_locations: Mapped[List["ItemLocation"]] = relationship("ItemLocation", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(telegram_id={self.telegram_id}, full_name='{self.full_name}', is_admin={self.is_admin})>"


class FuelLog(Base):
    """Модель записей о заправках автомобиля."""
    __tablename__ = "fuel_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    liters: Mapped[float] = mapped_column(Float, nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)
    station_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="fuel_logs")

    def __repr__(self) -> str:
        return f"<FuelLog(id={self.id}, liters={self.liters}, cost={self.cost}, odometer={self.odometer})>"


class ServiceLog(Base):
    """Модель записей о техническом обслуживании и ремонте."""
    __tablename__ = "service_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    odometer: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="service_logs")

    def __repr__(self) -> str:
        return f"<ServiceLog(id={self.id}, odometer={self.odometer}, title='{self.title}', cost={self.cost})>"


class ItemLocation(Base):
    """Модель учета вещей (инструменты, детали, сезонные вещи) в гараже или на даче."""
    __tablename__ = "item_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="item_locations")

    def __repr__(self) -> str:
        return f"<ItemLocation(id={self.id}, item_name='{self.item_name}', location='{self.location}')>"
