from dataclasses import dataclass
from datetime import datetime


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
