import enum
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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
    origin: str           # IATA code
    destination: str      # IATA code
    date: str             # YYYY-MM-DD
    price: int            # in BRL
    airline: str
    duration_min: int
    stops: int
    departure_time: str   # HH:MM
    arrival_time: str     # HH:MM
    fetched_at: datetime


class ScanStatus(enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SearchType(enum.Enum):
    ONEWAY = "oneway"
    ROUNDTRIP = "roundtrip"


class SearchConfig(Base):
    __tablename__ = "search_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)          # IATA
    destination: Mapped[str] = mapped_column(String(3), nullable=False)      # IATA
    must_arrive_by: Mapped[date] = mapped_column(Date, nullable=False)
    must_stay_until: Mapped[date] = mapped_column(Date, nullable=False)
    max_trip_days: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    scan_runs: Mapped[list["ScanRun"]] = relationship(back_populates="search_config")

    __table_args__ = (
        Index("ix_search_configs_origin_dest", "origin", "destination"),
    )


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_config_id: Mapped[int] = mapped_column(ForeignKey("search_configs.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ScanStatus] = mapped_column(Enum(ScanStatus, native_enum=False), nullable=False, server_default=ScanStatus.RUNNING.value)
    last_successful_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    search_config: Mapped["SearchConfig"] = relationship(back_populates="scan_runs")
    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="scan_run")

    __table_args__ = (
        Index("ix_scan_runs_config_id", "search_config_id"),
        Index("ix_scan_runs_status", "status"),
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)
    flight_code: Mapped[str] = mapped_column(String(20), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    stops: Mapped[int] = mapped_column(Integer, nullable=False)
    brand: Mapped[str] = mapped_column(String(30), nullable=False)           # LIGHT/STANDARD/FULL/PREMIUM ECONOMY
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)         # ISO 4217
    search_type: Mapped[SearchType] = mapped_column(Enum(SearchType, native_enum=False), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    scan_run: Mapped["ScanRun"] = relationship(back_populates="price_snapshots")

    __table_args__ = (
        Index("ix_price_snapshots_run_id", "scan_run_id"),
        Index("ix_price_snapshots_route_date", "origin", "destination", "flight_date"),
    )
