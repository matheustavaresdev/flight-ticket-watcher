import enum
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from flight_watcher.errors import ErrorCategory

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flight_watcher.db import Base


@dataclass
class FlightResult:
    origin: str  # IATA code
    destination: str  # IATA code
    date: str  # YYYY-MM-DD
    price: int  # in BRL
    airline: str
    duration_min: int
    stops: int
    departure_time: str  # HH:MM
    arrival_time: str  # HH:MM
    fetched_at: datetime


T = TypeVar("T")


@dataclass
class SearchResult(Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    error_category: "ErrorCategory | None" = None
    hint: str | None = None
    duration_sec: float = 0.0

    @classmethod
    def success(cls, data: T, duration_sec: float = 0.0) -> "SearchResult[T]":
        return cls(ok=True, data=data, duration_sec=duration_sec)

    @classmethod
    def failure(
        cls,
        error: str,
        error_category: "ErrorCategory | None" = None,
        hint: str | None = None,
        duration_sec: float = 0.0,
    ) -> "SearchResult[T]":
        return cls(
            ok=False,
            error=error,
            error_category=error_category,
            hint=hint,
            duration_sec=duration_sec,
        )


class ScanStatus(enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SearchType(enum.Enum):
    ONEWAY = "oneway"
    ROUNDTRIP = "roundtrip"


class AlertType(enum.Enum):
    NEW_LOW = "new_low"
    THRESHOLD = "threshold"


class SearchConfig(Base):
    __tablename__ = "search_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)  # IATA
    destination: Mapped[str] = mapped_column(String(3), nullable=False)  # IATA
    must_arrive_by: Mapped[date] = mapped_column(Date, nullable=False)
    must_stay_until: Mapped[date] = mapped_column(Date, nullable=False)
    max_trip_days: Mapped[int] = mapped_column(Integer, nullable=False)
    min_trip_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    needs_attention: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    scan_runs: Mapped[list["ScanRun"]] = relationship(back_populates="search_config")
    price_alerts: Mapped[list["PriceAlert"]] = relationship(back_populates="search_config")

    __table_args__ = (
        Index("ix_search_configs_origin_dest", "origin", "destination"),
        CheckConstraint(
            "min_trip_days IS NULL OR min_trip_days >= 1",
            name="ck_search_configs_min_trip_days_positive",
        ),
        CheckConstraint(
            "min_trip_days IS NULL OR min_trip_days <= max_trip_days",
            name="ck_search_configs_min_le_max_trip_days",
        ),
    )


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_config_id: Mapped[int] = mapped_column(
        ForeignKey("search_configs.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[ScanStatus] = mapped_column(
        Enum(
            ScanStatus,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
            validate_strings=True,
        ),
        nullable=False,
        server_default=ScanStatus.RUNNING.value,
    )
    last_successful_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    search_config: Mapped["SearchConfig"] = relationship(back_populates="scan_runs")
    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(
        back_populates="scan_run"
    )

    __table_args__ = (
        Index("ix_scan_runs_config_status", "search_config_id", "status"),
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)
    flight_code: Mapped[str] = mapped_column(String(20), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    arrival_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    stops: Mapped[int] = mapped_column(Integer, nullable=False)
    brand: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # LIGHT/STANDARD/FULL/PREMIUM ECONOMY
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217
    search_type: Mapped[SearchType] = mapped_column(
        Enum(
            SearchType,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
            validate_strings=True,
        ),
        nullable=False,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scan_run: Mapped["ScanRun"] = relationship(back_populates="price_snapshots")

    __table_args__ = (
        Index("ix_price_snapshots_run_id", "scan_run_id"),
        Index("ix_price_snapshots_route_date", "origin", "destination", "flight_date"),
        Index(
            "ix_price_snapshots_route_date_brand",
            "origin",
            "destination",
            "flight_date",
            "brand",
        ),
        Index("ix_price_snapshots_date_fetched", "flight_date", "fetched_at"),
    )


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_config_id: Mapped[int] = mapped_column(
        ForeignKey("search_configs.id"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)
    airline: Mapped[str] = mapped_column(String(30), nullable=False)
    brand: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_low_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_drop_abs: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(
            AlertType,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
            validate_strings=True,
        ),
        nullable=False,
    )
    sent_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    search_config: Mapped["SearchConfig"] = relationship(back_populates="price_alerts")

    __table_args__ = (
        Index("ix_price_alerts_route_date", "origin", "destination", "flight_date", "brand"),
    )
