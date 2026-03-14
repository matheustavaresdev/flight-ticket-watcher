"""Query functions for flight price analysis."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from flight_watcher.models import (
    PriceSnapshot,
    ScanRun,
    SearchConfig,
    ScanStatus,
    SearchType,
)


def get_latest_snapshots(
    session: Session,
    search_config_id: int,
    search_type: Optional[SearchType] = None,
    brand: str = "LIGHT",
) -> list[PriceSnapshot]:
    """Return snapshots with the latest fetched_at per unique (origin, dest, flight_date, flight_code, brand, search_type)."""
    subq_filters = [
        ScanRun.search_config_id == search_config_id,
        ScanRun.status == ScanStatus.COMPLETED,
        PriceSnapshot.brand == brand,
    ]
    if search_type is not None:
        subq_filters.append(PriceSnapshot.search_type == search_type)

    subq = (
        select(
            PriceSnapshot.origin,
            PriceSnapshot.destination,
            PriceSnapshot.flight_date,
            PriceSnapshot.flight_code,
            PriceSnapshot.brand,
            PriceSnapshot.search_type,
            func.max(PriceSnapshot.fetched_at).label("max_fetched_at"),
        )
        .join(ScanRun, PriceSnapshot.scan_run_id == ScanRun.id)
        .where(*subq_filters)
        .group_by(
            PriceSnapshot.origin,
            PriceSnapshot.destination,
            PriceSnapshot.flight_date,
            PriceSnapshot.flight_code,
            PriceSnapshot.brand,
            PriceSnapshot.search_type,
        )
        .subquery()
    )

    stmt = (
        select(PriceSnapshot)
        .join(ScanRun, PriceSnapshot.scan_run_id == ScanRun.id)
        .join(
            subq,
            and_(
                PriceSnapshot.origin == subq.c.origin,
                PriceSnapshot.destination == subq.c.destination,
                PriceSnapshot.flight_date == subq.c.flight_date,
                PriceSnapshot.flight_code == subq.c.flight_code,
                PriceSnapshot.brand == subq.c.brand,
                PriceSnapshot.search_type == subq.c.search_type,
                PriceSnapshot.fetched_at == subq.c.max_fetched_at,
            ),
        )
        .where(ScanRun.search_config_id == search_config_id)
    )

    return list(session.execute(stmt).scalars())


def best_combinations(
    session: Session,
    search_config_id: int,
    brand: str = "LIGHT",
    limit: int = 20,
) -> list[dict]:
    """
    Return cheapest (outbound, return) pairs ranked by total price.
    Groups by trip_days keeping only cheapest per stay length.
    Each dict has: outbound_date, return_date, trip_days, outbound_price, return_price, total_price, currency.
    """
    config = session.get(SearchConfig, search_config_id)
    if config is None:
        return []

    all_snaps = get_latest_snapshots(
        session, search_config_id, SearchType.ONEWAY, brand
    )

    # Cheapest price per date for outbound direction
    cheapest_out: dict[date, tuple[Decimal, str]] = {}
    for s in all_snaps:
        if s.origin == config.origin and s.destination == config.destination:
            if s.flight_date <= config.must_arrive_by:
                existing = cheapest_out.get(s.flight_date)
                if existing is None or s.price < existing[0]:
                    cheapest_out[s.flight_date] = (s.price, s.currency)

    # Cheapest price per date for return direction
    cheapest_ret: dict[date, tuple[Decimal, str]] = {}
    for s in all_snaps:
        if s.origin == config.destination and s.destination == config.origin:
            if s.flight_date >= config.must_stay_until:
                existing = cheapest_ret.get(s.flight_date)
                if existing is None or s.price < existing[0]:
                    cheapest_ret[s.flight_date] = (s.price, s.currency)

    # Cross-join: group by trip_days keeping cheapest
    results_by_trip_days: dict[int, dict] = {}
    for out_date, (out_price, currency) in cheapest_out.items():
        for ret_date, (ret_price, _) in cheapest_ret.items():
            trip_days = (ret_date - out_date).days
            if trip_days < 0 or trip_days > config.max_trip_days:
                continue
            total_price = out_price + ret_price
            existing = results_by_trip_days.get(trip_days)
            if existing is None or total_price < existing["total_price"]:
                results_by_trip_days[trip_days] = {
                    "outbound_date": out_date,
                    "return_date": ret_date,
                    "trip_days": trip_days,
                    "outbound_price": out_price,
                    "return_price": ret_price,
                    "total_price": total_price,
                    "currency": currency,
                }

    return sorted(results_by_trip_days.values(), key=lambda r: r["total_price"])[:limit]


def roundtrip_vs_oneway(
    session: Session,
    search_config_id: int,
    brand: str = "LIGHT",
) -> list[dict]:
    """
    Compare booking as roundtrip vs 2 one-ways for each (outbound_date, return_date) pair.
    Only returns pairs with data in all four combinations (RT-out, RT-ret, OW-out, OW-ret).
    Each dict has: outbound_date, return_date, roundtrip_total, oneway_total, savings_pct, recommendation, significant.
    """
    config = session.get(SearchConfig, search_config_id)
    if config is None:
        return []

    all_snaps = get_latest_snapshots(session, search_config_id, brand=brand)

    # Build cheapest-per-date dicts for each combination
    rt_out: dict[date, Decimal] = {}
    rt_ret: dict[date, Decimal] = {}
    ow_out: dict[date, Decimal] = {}
    ow_ret: dict[date, Decimal] = {}

    for s in all_snaps:
        is_out_dir = s.origin == config.origin and s.destination == config.destination
        is_ret_dir = s.origin == config.destination and s.destination == config.origin

        if is_out_dir:
            target = rt_out if s.search_type == SearchType.ROUNDTRIP else ow_out
        elif is_ret_dir:
            target = rt_ret if s.search_type == SearchType.ROUNDTRIP else ow_ret
        else:
            continue

        existing = target.get(s.flight_date)
        if existing is None or s.price < existing:
            target[s.flight_date] = s.price

    # Date pairs that have all four components
    out_dates = set(rt_out) & set(ow_out)
    ret_dates = set(rt_ret) & set(ow_ret)

    # Cartesian product of all observed outbound × return dates. Legs are stored
    # independently without a pairing key, so this may include date pairs that were
    # never searched as a single roundtrip — a known approximation.
    results = []
    for out_date in sorted(out_dates):
        for ret_date in sorted(ret_dates):
            trip_days = (ret_date - out_date).days
            if trip_days < 0 or trip_days > config.max_trip_days:
                continue
            rt_total = rt_out[out_date] + rt_ret[ret_date]
            ow_total = ow_out[out_date] + ow_ret[ret_date]
            max_total = max(rt_total, ow_total)
            savings_pct = (
                float(abs(rt_total - ow_total) / max_total * 100)
                if max_total > 0
                else 0.0
            )
            results.append(
                {
                    "outbound_date": out_date,
                    "return_date": ret_date,
                    "roundtrip_total": rt_total,
                    "oneway_total": ow_total,
                    "savings_pct": savings_pct,
                    "recommendation": "roundtrip"
                    if rt_total <= ow_total
                    else "2x one-way",
                    "significant": savings_pct > 5,
                }
            )

    return results


@dataclass
class PriceHistoryResult:
    snapshots: list[PriceSnapshot]  # ordered by fetched_at ascending
    min_price: Decimal
    max_price: Decimal
    avg_price: Decimal
    min_price_seen_at: datetime  # fetched_at of the cheapest snapshot


def price_history(
    session: Session,
    origin: str,
    destination: str,
    flight_date: date,
    brand: str = "LIGHT",
    search_type: SearchType | None = None,
) -> PriceHistoryResult | None:
    """Return price history for a specific route + date, ordered by fetched_at ascending.

    Only includes data from completed scan runs. Returns None if no snapshots found.
    """
    stmt = (
        select(PriceSnapshot)
        .join(ScanRun, PriceSnapshot.scan_run_id == ScanRun.id)
        .where(ScanRun.status == ScanStatus.COMPLETED)
        .where(PriceSnapshot.origin == origin)
        .where(PriceSnapshot.destination == destination)
        .where(PriceSnapshot.flight_date == flight_date)
        .where(PriceSnapshot.brand == brand)
        .order_by(PriceSnapshot.fetched_at)
    )

    if search_type is not None:
        stmt = stmt.where(PriceSnapshot.search_type == search_type)

    snapshots: list[PriceSnapshot] = session.execute(stmt).scalars().all()

    if not snapshots:
        return None

    prices = [s.price for s in snapshots]
    min_price = min(prices)
    max_price = max(prices)
    avg_price = sum(prices, Decimal("0")) / Decimal(len(prices))

    min_price_seen_at = next(s.fetched_at for s in snapshots if s.price == min_price)

    return PriceHistoryResult(
        snapshots=list(snapshots),
        min_price=min_price,
        max_price=max_price,
        avg_price=avg_price,
        min_price_seen_at=min_price_seen_at,
    )


def price_trend_summary(
    session: Session,
    search_config_id: int,
    brand: str = "LIGHT",
    search_type: SearchType = SearchType.ONEWAY,
) -> list[dict]:
    """Return price trend summary per flight_date for a search config.

    Each dict: {flight_date, current_price, rolling_avg_7d, direction, pct_diff}
    Direction: "↑" if pct_diff > 5, "↓" if pct_diff < -5, "→" otherwise
    Rolling avg uses last 7 observations (or all if < 7).
    Sorted by flight_date.
    """
    stmt = (
        select(PriceSnapshot)
        .join(ScanRun, PriceSnapshot.scan_run_id == ScanRun.id)
        .where(ScanRun.search_config_id == search_config_id)
        .where(ScanRun.status == ScanStatus.COMPLETED)
        .where(PriceSnapshot.brand == brand)
        .where(PriceSnapshot.search_type == search_type)
        .order_by(PriceSnapshot.fetched_at)
    )

    snapshots: list[PriceSnapshot] = session.execute(stmt).scalars().all()

    if not snapshots:
        return []

    # Reduce to one price per (scan_run_id, flight_date) — take min price (best deal seen in that scan)
    run_date_best: dict[tuple[int, date], tuple[datetime, Decimal]] = {}
    for s in snapshots:
        key = (s.scan_run_id, s.flight_date)
        if key not in run_date_best or s.price < run_date_best[key][1]:
            run_date_best[key] = (s.fetched_at, s.price)

    # Build time series: one entry per (scan_run, flight_date), sorted by fetched_at within each date
    groups: dict[date, list[tuple[datetime, Decimal]]] = defaultdict(list)
    for (_, flight_date), (fetched_at, price) in sorted(
        run_date_best.items(), key=lambda x: x[1][0]
    ):
        groups[flight_date].append((fetched_at, price))

    results = []
    for flight_date in sorted(groups):
        entries = groups[flight_date]  # already ordered by fetched_at (query ORDER BY)
        prices = [price for _, price in entries]

        current_price = prices[-1]
        last_7 = prices[-7:]
        rolling_avg_7d = sum(last_7, Decimal("0")) / Decimal(len(last_7))

        if rolling_avg_7d == Decimal("0"):
            pct_diff = 0.0
            direction = "→"
        else:
            pct_diff = float(
                (current_price - rolling_avg_7d) / rolling_avg_7d * Decimal("100")
            )
            if pct_diff > 5:
                direction = "↑"
            elif pct_diff < -5:
                direction = "↓"
            else:
                direction = "→"

        results.append(
            {
                "flight_date": flight_date,
                "current_price": current_price,
                "rolling_avg_7d": rolling_avg_7d,
                "direction": direction,
                "pct_diff": pct_diff,
            }
        )

    return results
