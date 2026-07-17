#!/usr/bin/env python3
"""Backfill daily Max Energy station-median fuel history."""
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import fuel_history
from dashboard import generate_dashboard
from scrapers import fuel

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "data" / "history" / "fuel.csv"
def _retrieval_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dates(end: date, days: int) -> list[date]:
    start = end - timedelta(days=days - 1)
    return [start + timedelta(days=offset) for offset in range(days)]


def _read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        if not row.get("source"):
            row["source"] = (
                fuel_history.MAX_ENERGY_SOURCE
                if row.get("as_of", "")[:4].isdigit()
                else "GlobalPetrolPrices.com (legacy weekly national average)"
            )
        row["provenance"] = row.get("provenance") or fuel_history.PROVENANCE_SCHEDULED
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fuel_history.FIELDNAMES)
        writer.writeheader()
        writer.writerows(
            {field: row.get(field, "") for field in fuel_history.FIELDNAMES} for row in rows
        )
    temporary.replace(path)


def backfill(days: int, end: date, workers: int, output: Path = DEFAULT_OUTPUT) -> int:
    if days < 1:
        raise ValueError("days must be positive")
    existing = _read_existing(output)
    existing_dates = {
        row["as_of"]
        for row in existing
        if row.get("source", "").startswith("Max Energy")
    }
    requested = [day for day in _dates(end, days) if day.isoformat() not in existing_dates]

    fetched_rows = []
    failures = []
    if requested:
        retrieved_at_utc = _retrieval_timestamp()
        api_config = fuel.discover_api_config()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(fuel.fetch_for_date, day, api_config=api_config): day
                for day in requested
            }
            for future in as_completed(futures):
                day = futures[future]
                result = future.result()
                if result["errors"] or not result["data"]:
                    failures.append((day, result["errors"]))
                    continue
                data = result["data"]
                if data.get("as_of") != day.isoformat():
                    failures.append(
                        (
                            day,
                            [
                                "Max Energy returned source date "
                                f"{data.get('as_of')!r} for requested date {day.isoformat()}"
                            ],
                        )
                    )
                    continue
                # Retrieval time is intentionally distinct from the API's
                # historical source date in `as_of`.
                fetched_rows.append(
                    fuel_history.serialize(
                        data,
                        ts_utc=retrieved_at_utc,
                        provenance=fuel_history.PROVENANCE_BACKFILL,
                        include_usd=False,
                    )
                )

    by_source_date = {(row.get("source"), row.get("as_of")): row for row in fetched_rows}
    # Existing scheduled observations take precedence over a same-day backfill.
    for row in existing:
        by_source_date[(row.get("source"), row.get("as_of"))] = row
    rows = sorted(by_source_date.values(), key=lambda row: (row.get("as_of", ""), row.get("source", "")))
    _write_rows(output, rows)
    generate_dashboard(data_dir=ROOT / "data", output_path=ROOT / "dashboard" / "market-trends.svg")

    print(f"backfilled {len(fetched_rows)} day(s); {len(existing_dates)} existing day(s) preserved")
    for day, errors in sorted(failures):
        print(f"FAILED {day}: {'; '.join(errors)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="inclusive lookback window")
    parser.add_argument("--end", type=date.fromisoformat, default=datetime.now(fuel.YANGON_TZ).date())
    parser.add_argument("--workers", type=int, default=7)
    args = parser.parse_args()
    return backfill(args.days, args.end, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
