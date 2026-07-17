# README market dashboard and source-specific schedules

The README now embeds a generated SVG dashboard built from committed snapshots
and history. It focuses on metrics specific to the repository's Myanmar market
purpose: P2P market FX and Max Energy fuel prices. International gold is no
longer displayed or refreshed automatically; its existing files remain as
legacy data for compatibility.

The dashboard uses current-value cards and 30-day trend panels. It waits for at
least eight comparable observations before drawing a line. Fuel has been seeded
with 30 genuine daily Max Energy observations, while market FX begins with the
repository's first collected P2P observation because no equivalent public daily
history exists.

Fuel backfill rows carry explicit `source` and `provenance` fields. Historical
MMK pump prices are retained, but historical USD equivalents remain blank
because there is no matching historical P2P FX series.

Automated collection is split by source behavior:

- market FX every six hours;
- Max Energy fuel daily at 08:17 Myanmar time.

Both workflows regenerate and commit the dashboard after updating their own
dataset. `update.py --topics ...` provides the same selective behavior locally,
and `backfill_fuel.py` makes the daily Max Energy history seed reproducible.
