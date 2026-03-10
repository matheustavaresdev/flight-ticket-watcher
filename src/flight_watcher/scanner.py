import logging
from datetime import datetime

from fast_flights import FlightQuery, Passengers, create_query, get_flights

from flight_watcher.circuit_breaker import get_breaker
from flight_watcher.delays import random_delay
from flight_watcher.errors import classify_error, get_retry_strategy
from flight_watcher.models import FlightResult

logger = logging.getLogger(__name__)


def search_one_way(
    origin: str,
    destination: str,
    date: str,
    passengers: int = 1,
) -> list[FlightResult]:
    """Search one-way flights and return a list of FlightResult."""
    breaker = get_breaker()
    if not breaker.allow_request():
        logger.warning("Circuit breaker OPEN — skipping search %s→%s on %s", origin, destination, date)
        return []
    for attempt in range(3):
        try:
            query = create_query(
                flights=[FlightQuery(date=date, from_airport=origin, to_airport=destination)],
                trip="one-way",
                passengers=Passengers(adults=passengers),
                currency="BRL",
            )
            flights_obj = get_flights(query)
            results = _map_flight_to_results(flights_obj, origin, destination, date)
            breaker.record_success()
            return results
        except Exception as exc:
            category = classify_error(exc)
            breaker.record_failure(category)
            if not breaker.allow_request():
                logger.warning("Circuit breaker tripped — aborting remaining retries")
                break
            strategy = get_retry_strategy(category)
            if strategy.skip_item:
                logger.warning(
                    "search_one_way %s→%s %s: %s (category=%s) — skipping",
                    origin, destination, date, exc, category.value,
                )
                return []
            if attempt < strategy.max_retries:
                wait = random_delay(strategy.min_delay_sec, strategy.max_delay_sec)
                logger.warning(
                    "search_one_way %s→%s %s failed (attempt %d/%d, category=%s): %s — retried after %.0fs",
                    origin, destination, date, attempt + 1, strategy.max_retries, category.value, exc, wait,
                )
            else:
                logger.error(
                    "search_one_way %s→%s %s failed after %d attempts (category=%s): %s",
                    origin, destination, date, attempt + 1, category.value, exc,
                )
                break
    return []


def search_roundtrip(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    passengers: int = 1,
) -> tuple[list[FlightResult], list[FlightResult]]:
    """Search round-trip flights. Returns (outbound_results, return_results)."""
    outbound = search_one_way(origin, destination, departure_date, passengers)
    random_delay()
    inbound = search_one_way(destination, origin, return_date, passengers)
    return outbound, inbound


def _map_flight_to_results(
    flights_obj,
    origin: str,
    destination: str,
    date: str,
) -> list[FlightResult]:
    """Convert a Flights object from fast-flights to a list of FlightResult."""
    results = []
    for flight in flights_obj:
        try:
            stops = len(flight.flights) - 1
            airline = ", ".join(flight.airlines)
            dep_h, dep_m = flight.flights[0].departure.time
            arr_h, arr_m = flight.flights[-1].arrival.time
            departure_time = f"{dep_h:02d}:{dep_m:02d}"
            arrival_time = f"{arr_h:02d}:{arr_m:02d}"
            results.append(
                FlightResult(
                    origin=origin,
                    destination=destination,
                    date=date,
                    price=flight.price,
                    airline=airline,
                    duration_min=sum(seg.duration for seg in flight.flights),
                    stops=stops,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    fetched_at=datetime.now(),
                )
            )
        except Exception as exc:
            logger.warning("Skipping flight result due to mapping error: %s", exc)
    return results
