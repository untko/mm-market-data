---
title: SuperRich Thailand retail cash FX source
date: 2026-07-19
status: implemented
---

# SuperRich Thailand retail cash FX source

The FX collector now records SuperRich Thailand cash-counter quotes for USD/THB,
GBP/THB, EUR/THB, JPY/THB, and CNY/THB. This feed remains separate from the
existing Binance P2P proxy because a retail cash spread and a P2P market rate are
different market observations.

The collector uses the same read-only rates endpoint as the SuperRich website.
For each currency, it retains the site's primary advertised banknote denomination
and the buy, sell, and calculated midpoint in THB per unit of foreign currency.
Buying and selling are explicitly from SuperRich's perspective.

Current values are stored under `fx.retail_cash` in the exchange-rate snapshots.
Changed denomination/buy/sell sets are appended to
`data/history/superrich_thailand.csv`; unchanged sets are deduplicated in line
with the repository's other change histories.

The endpoint's `dateTime` currently looks like Thailand wall-clock time with a
misleading `Z` suffix. It is therefore preserved only as
`source_updated_at_raw`. Snapshot `updated_at_utc` and history `ts_utc` remain the
trustworthy collector timestamps for freshness and ordering.
