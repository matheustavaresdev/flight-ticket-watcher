"""Shared CLI input validators for IATA codes and ISO dates."""

import re
from datetime import date

import typer

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iata(value: str) -> str:
    code = value.upper()
    if len(code) != 3 or not code.isalpha():
        raise typer.BadParameter(
            f"Invalid IATA code '{value}': must be exactly 3 alphabetic characters."
        )
    return code


def parse_date(value: str) -> date:
    if not _DATE_RE.match(value):
        raise typer.BadParameter(f"Invalid date '{value}': expected format YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(f"Invalid date '{value}': expected format YYYY-MM-DD.")
