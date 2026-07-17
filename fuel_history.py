"""Shared schema and parsing helpers for committed fuel history."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, tzinfo
from pathlib import Path

MAX_ENERGY_SOURCE = "Max Energy Myanmar daily station prices (median across stations)"
PROVENANCE_BACKFILL = "backfill"
PROVENANCE_SCHEDULED = "scheduled"
VALID_PROVENANCE = frozenset({PROVENANCE_BACKFILL, PROVENANCE_SCHEDULED})

FIELDNAMES = (
    "ts_utc",
    "as_of",
    "gasoline_95_usd_per_litre",
    "diesel_usd_per_litre",
    "gasoline_95_mmk_per_litre_market",
    "diesel_mmk_per_litre_market",
    "source",
    "provenance",
)


@dataclass(frozen=True)
class FuelHistoryPoint:
    source_timestamp: datetime
    gasoline_95_mmk: float
    diesel_mmk: float
    provenance: str


def serialize(observation: dict, *, ts_utc: str, provenance: str, include_usd: bool) -> dict:
    if provenance not in VALID_PROVENANCE:
        raise ValueError(f"unknown fuel-history provenance: {provenance}")
    return {
        "ts_utc": ts_utc,
        "as_of": observation.get("as_of"),
        "gasoline_95_usd_per_litre": (
            observation.get("gasoline_95_usd_per_litre") if include_usd else ""
        ),
        "diesel_usd_per_litre": (
            observation.get("diesel_usd_per_litre") if include_usd else ""
        ),
        "gasoline_95_mmk_per_litre_market": observation.get(
            "gasoline_95_mmk_per_litre_market"
        ),
        "diesel_mmk_per_litre_market": observation.get("diesel_mmk_per_litre_market"),
        "source": observation.get("source"),
        "provenance": provenance,
    }


def _parse_max_energy_row(row: dict, source_timezone: tzinfo) -> FuelHistoryPoint | None:
    try:
        if row["source"] != MAX_ENERGY_SOURCE or row["provenance"] not in VALID_PROVENANCE:
            return None
        source_date = date.fromisoformat(row["as_of"])
        return FuelHistoryPoint(
            source_timestamp=datetime.combine(source_date, time.min, tzinfo=source_timezone),
            gasoline_95_mmk=float(row["gasoline_95_mmk_per_litre_market"]),
            diesel_mmk=float(row["diesel_mmk_per_litre_market"]),
            provenance=row["provenance"],
        )
    except (KeyError, TypeError, ValueError):
        return None


def read_max_energy_points(path: Path, source_timezone: tzinfo) -> list[FuelHistoryPoint]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            point
            for row in csv.DictReader(fh)
            if (point := _parse_max_energy_row(row, source_timezone)) is not None
        ]
