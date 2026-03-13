"""Browser fingerprint profiles for anti-detection rotation."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserProfile:
    locale: str
    timezone_id: str
    viewport_width: int
    viewport_height: int


# Coherent Brazilian user profiles
PROFILES: list[BrowserProfile] = [
    BrowserProfile(locale="pt-BR", timezone_id="America/Sao_Paulo", viewport_width=1920, viewport_height=1080),
    BrowserProfile(locale="pt-BR", timezone_id="America/Sao_Paulo", viewport_width=1366, viewport_height=768),
    BrowserProfile(locale="pt-BR", timezone_id="America/Sao_Paulo", viewport_width=1440, viewport_height=900),
    BrowserProfile(locale="pt-BR", timezone_id="America/Fortaleza", viewport_width=1920, viewport_height=1080),
    BrowserProfile(locale="pt-BR", timezone_id="America/Fortaleza", viewport_width=1366, viewport_height=768),
    BrowserProfile(locale="pt-BR", timezone_id="America/Fortaleza", viewport_width=1440, viewport_height=900),
    BrowserProfile(locale="en-US", timezone_id="America/Sao_Paulo", viewport_width=1920, viewport_height=1080),
    BrowserProfile(locale="en-US", timezone_id="America/Sao_Paulo", viewport_width=1366, viewport_height=768),
    BrowserProfile(locale="en-US", timezone_id="America/Sao_Paulo", viewport_width=1440, viewport_height=900),
]


def get_random_profile() -> BrowserProfile:
    """Select a random browser fingerprint profile."""
    return random.choice(PROFILES)
