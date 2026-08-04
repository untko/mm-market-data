---
title: Market dashboard trends and source observation history
date: 2026-08-04
status: implemented
---

# Market dashboard trends and source observation history

The README dashboard now keeps time-series panels consistent. USD/MMK is rendered
as a line trend with a dashed CBM official-reference line, including the latest
market snapshot while history is sparse. The SuperRich Thailand cash row uses
buy-only 30-day sparklines for USD, GBP, EUR, JPY, and CNY.

The market FX history previously deduplicated unchanged values, so successful
six-hour pulls could update `latest.json` without adding observations to
`data/history/exchange_rates.csv`. FX history now keeps timestamped observations
so a flat market remains visibly flat for the correct reason while the series
continues to accumulate coverage.

The `superrich.tech/api/p2p-rates` response does not include a source freshness
timestamp. The collector records its own collection time and source errors, but
cannot independently distinguish an unchanged market from a silently frozen
upstream response without a second market source or additional source-health
telemetry.
