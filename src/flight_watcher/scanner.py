import logging
import time
from datetime import datetime

from fast_flights import FlightQuery, Passengers, create_query, get_flights

from flight_watcher.models import FlightResult

logger = logging.getLogger(__name__)


def search_one_way(
    origin: str,
    destination: str,
    date: str,
    passengers: int = 1,
) -> list[FlightResult]:
    """Search one-way flights and return a list of FlightResult."""
    for attempt in range(3):
        try:
            query = create_query(
                flights=[FlightQuery(date=date, from_airport=origin, to_airport=destination)],
                trip="one-way",
                passengers=Passengers(adults=passengers),
                currency="BRL",
            )
            flights_obj = get_flights(query)
            return _map_flight_to_results(flights_obj, origin, destination, date)
        except Exception as exc:
            if attempt < 2:
                wait = 2 ** attempt
                logger.warning(
                    "search_one_way %s→%s %s failed (attempt %d/3): %s — retrying in %ds",
                    origin, destination, date, attempt + 1, exc, wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "search_one_way %s→%s %s failed after 3 attempts: %s",
                    origin, destination, date, exc,
                )
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
    time.sleep(2)
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
