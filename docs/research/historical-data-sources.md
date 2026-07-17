# Historical Myanmar market USD/MMK sources

Research date: 2026-07-17

## Conclusion

I did not find a public historical **daily** series that is semantically identical to this repository's current market-rate metric: a current USDT/MMK P2P quote derived from SuperRich's aggregation or, as fallback, the median of the top ten Binance P2P `SELL` advertisements.

The strongest defensible background dataset is the World Bank's monthly Myanmar **parallel-market estimate**. It covers 2007 onward and is openly downloadable, but it is modeled, monthly, and geographically disaggregated. It should therefore be displayed as a separate historical series with a visible source/method break, not inserted into `data/history/exchange_rates.csv` as if this repository had observed the P2P metric on those dates.

## Source assessment

| Source | Historical support and coverage | Authentication / cost | Comparable to the current metric? | Recommendation |
|---|---|---|---|---|
| SuperRich `p2p-rates` | No historical interface was found. The [live endpoint](https://superrich.tech/api/p2p-rates) returns only a current currency-to-rate map, with no observation timestamp or history. Supplying a [past `date` query](https://superrich.tech/api/p2p-rates?date=2025-01-01) returned the same live-shaped response when tested. The site's published JavaScript bundle exposes `p2p-rates` but no history route; its chart fabricates a visual history by scaling Binance `USDTBRL` klines with the current MMK rate rather than retrieving historical MMK P2P observations ([published bundle observed on 2026-07-17](https://superrich.tech/assets/index-BxIaKonW.js)). | Public endpoint; no key or payment requested. It is undocumented, so there is no published retention or service guarantee. | Exact live upstream used by the repo, but no usable historical data. The site's chart is not historical USD/MMK evidence. | Keep collecting prospectively; do not backfill from the chart. |
| Binance public P2P advertisement search | The repo's fallback calls Binance's current advertisement-search route. Binance does not document that route as a historical market-data API, and direct requests expose current ads rather than a dated market series. | The current-ad route accepts an unauthenticated request, but is undocumented and may return no results or be geographically blocked. | Exact market mechanism for the repo's fallback, but no historical daily observations. | Keep collecting prospectively; no defensible backfill found. |
| Binance official C2C trade history | Binance documents one historical C2C endpoint, but it returns only the authenticated user's orders. Requests can span at most 30 days and API access is limited to the past six months ([Binance C2C API documentation](https://developers.binance.com/en/docs/catalog/investment-and-services-c2-c/api/rest-api/~#get-c2-ctrade-history)). | Requires a Binance API key and user account. | No. These are one user's executed trades, not the public top-ad median or a market-wide quote. | Reject as dashboard backfill. |
| World Bank Real-Time Exchange Rates (RTFX), Myanmar | Monthly market-level estimates from 2007-01-01 to 2026-07-01 in the 2026-07-06 release, covering 293 markets ([Myanmar catalog record](https://microdata.worldbank.org/catalog/6150/study-description)). The current download manifest labels the files open data and provides a no-login download/API route ([download manifest](https://microdata.worldbank.org/api/downloads/MMR_2023_RTFX_v01_M/files?type=data)). | Open data; no API key or paid plan indicated. | Conceptually close but not identical. The Myanmar ticker is explicitly an "Unofficial exchange rate (Parallel-market Estimate)(FAO GIEWS completed with Int. Forex)" in USD/LCU. The World Bank says the series combines direct data with machine-learning estimates, smooths outliers, and is continually revised. It is monthly and subnational, whereas the repo metric is a current USDT/MMK P2P-ad proxy. | Best source for a **separate monthly background line**. Use the `Market Average` geography or document another aggregation, and pin the downloaded version. Do not splice it into the P2P line. |
| Myanmar Currency API | Its [public repository](https://github.com/myanmar-currency-api/myanmar-currency-api.github.io/tree/main/api/2024) contains 98 dated JSON snapshots from [2024-02-07](https://myanmar-currency-api.github.io/api/2024/02/07/latest.json) through [2024-06-21](https://myanmar-currency-api.github.io/api/2024/06/21/latest.json). The project documents a latest endpoint and says there are no request limits ([project API documentation](https://myanmar-currency-api.github.io/)). | Public, no key, and no stated request limit. | Only loosely comparable. It reports USD cash-market `buy` and `sell` values rather than P2P USDT advertisements, and describes provenance only as "reputable financial markets" supplemented by DVB news. The series is short and stopped in June 2024. | Do not use as the canonical backfill. At most show it as a separately labeled, experimental comparison series. |

## Recommended data treatment

If historical context is added, keep source identity in the data rather than making backfilled values appear to have been collected by this repository. A safe arrangement is a separate file such as `data/backfill/usd_mmk_parallel_world_bank_monthly.csv` with at least:

```text
date,usd_mmk,geography,source,source_version,frequency,observation_type,backfilled,retrieved_at_utc
```

For the README/dashboard:

- Plot the World Bank monthly parallel-market estimate as its own labeled line.
- Plot the repo's P2P proxy only from its first actual observation onward.
- Mark the methodology/source change explicitly; do not connect the two into one continuous series.
- Do not forward-fill or interpolate the World Bank monthly values into synthetic daily observations.
- Pin the World Bank release date in the committed data because the publisher revises historical estimates as new information arrives.

This gives useful background without implying that modeled monthly estimates and live P2P advertisements are the same measurement.
