#!/usr/bin/env python3
"""Generate the static SVG dashboard embedded in the repository README."""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import fuel_history

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_PATH = ROOT / "dashboard" / "market-trends.svg"

WIDTH = 1200
HEIGHT = 840
MIN_TREND_POINTS = 8
YANGON_TZ = timezone(timedelta(hours=6, minutes=30))
CASH_CURRENCIES = ("USD", "GBP", "EUR", "JPY", "CNY")
TREND_Y = 398
TREND_HEIGHT = 352

INK = "#172033"
MUTED = "#64748b"
GRID = "#dbe3ef"
PANEL = "#ffffff"
BACKGROUND = "#f6f8fc"
BLUE = "#2563eb"
ORANGE = "#e87817"
TEAL = "#0f9d75"


@dataclass(frozen=True)
class TrendSeries:
    label: str
    points: list[tuple[datetime, float]]
    color: str
    dash: str | None = None


@dataclass(frozen=True)
class DashboardModel:
    latest: dict
    updated: datetime
    market: dict
    official: dict
    retail_cash: dict
    fuel: dict
    fx_updated: datetime
    cash_updated: datetime
    fuel_updated: datetime
    fx_history: list[tuple[datetime, list[float]]]
    cash_history: dict[str, list[tuple[datetime, float]]]
    fuel_history: list[tuple[datetime, list[float]]]
    fuel_provenance: Counter[str]


def _number(value, decimals: int = 0) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{decimals}f}"


def _read_history(path: Path, fields: list[str]) -> list[tuple[datetime, list[float]]]:
    if not path.exists():
        return []
    points = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                timestamp = datetime.fromisoformat(row["ts_utc"])
                values = [float(row[field]) for field in fields]
            except (KeyError, TypeError, ValueError):
                continue
            points.append((timestamp, values))
    return points


def _window(points, end: datetime, days: int = 30):
    start = end - timedelta(days=days)
    return [point for point in points if start <= point[0] <= end]


def _read_cash_buy_history(
    path: Path, end: datetime, days: int = 30
) -> dict[str, list[tuple[datetime, float]]]:
    history = {currency: [] for currency in CASH_CURRENCIES}
    if not path.exists():
        return history
    start = end - timedelta(days=days)
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                timestamp = datetime.fromisoformat(row["ts_utc"])
            except (KeyError, TypeError, ValueError):
                continue
            if not start <= timestamp <= end:
                continue
            for currency in CASH_CURRENCIES:
                try:
                    value = float(row[f"{currency.lower()}_buy_thb_per_unit"])
                except (KeyError, TypeError, ValueError):
                    continue
                history[currency].append((timestamp, value))
    for points in history.values():
        points.sort(key=lambda point: point[0])
    return history


def _load_dashboard_model(data_dir: Path) -> DashboardModel:
    latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    updated = datetime.fromisoformat(latest["updated_at_utc"])

    def snapshot_updated(filename: str) -> datetime:
        path = data_dir / filename
        if not path.exists():
            return updated
        try:
            return datetime.fromisoformat(json.loads(path.read_text())["updated_at_utc"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return updated

    def fx_section_updated(section: str) -> datetime:
        path = data_dir / "exchange_rates.json"
        if not path.exists():
            return updated
        try:
            payload = json.loads(path.read_text())
            value = (payload.get(section) or {}).get("collected_at_utc")
            return datetime.fromisoformat(value or payload["updated_at_utc"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return updated

    window_start = updated - timedelta(days=30)
    fx_history = _window(
        _read_history(data_dir / "history" / "exchange_rates.csv", ["usd_mmk_market"]),
        updated,
    )
    latest_market = (latest.get("fx") or {}).get("market") or {}
    latest_market_timestamp = latest_market.get("collected_at_utc")
    if latest_market_timestamp and latest_market.get("USD_MMK") is not None:
        try:
            latest_market_point = (
                datetime.fromisoformat(latest_market_timestamp),
                [float(latest_market["USD_MMK"])],
            )
        except (TypeError, ValueError):
            latest_market_point = None
        if latest_market_point:
            timestamp = latest_market_point[0]
            if (
                window_start <= timestamp <= updated
                and not any(timestamp == point[0] for point in fx_history)
            ):
                fx_history.append(latest_market_point)
                fx_history.sort(key=lambda point: point[0])
    cash_history = _read_cash_buy_history(
        data_dir / "history" / "superrich_thailand.csv", updated
    )
    latest_cash = (latest.get("fx") or {}).get("retail_cash") or {}
    latest_cash_timestamp = latest_cash.get("collected_at_utc")
    if latest_cash_timestamp:
        try:
            cash_timestamp = datetime.fromisoformat(latest_cash_timestamp)
        except (TypeError, ValueError):
            cash_timestamp = None
        if cash_timestamp and window_start <= cash_timestamp <= updated:
            for currency in CASH_CURRENCIES:
                quote = (latest_cash.get("quotes") or {}).get(currency) or {}
                buying = quote.get("buy_thb_per_unit")
                try:
                    cash_value = float(buying)
                except (TypeError, ValueError):
                    continue
                if not any(
                    cash_timestamp == point[0] for point in cash_history[currency]
                ):
                    cash_history[currency].append((cash_timestamp, cash_value))
                    cash_history[currency].sort(key=lambda point: point[0])
    fuel_points = [
        point
        for point in fuel_history.read_max_energy_points(
            data_dir / "history" / "fuel.csv", source_timezone=YANGON_TZ
        )
        if window_start <= point.source_timestamp <= updated
    ]
    return DashboardModel(
        latest=latest,
        updated=updated,
        market=(latest.get("fx") or {}).get("market") or {},
        official=(latest.get("fx") or {}).get("official_reference") or {},
        retail_cash=(latest.get("fx") or {}).get("retail_cash") or {},
        fuel=latest.get("fuel") or {},
        fx_updated=fx_section_updated("market").astimezone(YANGON_TZ),
        cash_updated=fx_section_updated("retail_cash").astimezone(YANGON_TZ),
        fuel_updated=snapshot_updated("fuel.json").astimezone(YANGON_TZ),
        fx_history=fx_history,
        cash_history=cash_history,
        fuel_history=[
            (point.source_timestamp, [point.gasoline_95_mmk, point.diesel_mmk])
            for point in fuel_points
        ],
        fuel_provenance=Counter(point.provenance for point in fuel_points),
    )


def _text(x, y, content, css_class="", anchor="start") -> str:
    return (
        f'<text x="{x}" y="{y}" class="{css_class}" '
        f'text-anchor="{anchor}">{escape(str(content))}</text>'
    )


def _card(x, width, title, value, note, accent) -> str:
    return "".join(
        [
            f'<rect x="{x}" y="82" width="{width}" height="112" rx="12" class="panel"/>',
            f'<rect x="{x}" y="82" width="{width}" height="4" rx="2" fill="{accent}"/>',
            _text(x + 16, 111, title, "card-label"),
            _text(x + 16, 151, value, "card-value"),
            _text(x + 16, 178, note, "card-note"),
        ]
    )


def _sparkline(
    points: list[tuple[datetime, float]], x: float, y: float, width: float, height: float
) -> str:
    if not points:
        return _text(x, y + height / 2 + 4, "—", "cash-sparkline-empty")
    timestamps = [point[0] for point in points]
    values = [point[1] for point in points]
    min_time, max_time = min(timestamps), max(timestamps)
    min_value, max_value = min(values), max(values)
    value_padding = (max_value - min_value) * 0.18 or max(abs(min_value) * 0.01, 0.001)
    low, high = min_value - value_padding, max_value + value_padding

    def x_for_timestamp(timestamp):
        span = (max_time - min_time).total_seconds() or 1
        return x + (timestamp - min_time).total_seconds() / span * width

    def y_for_value(value):
        return y + (high - value) / (high - low) * height

    coords = " ".join(
        f"{x_for_timestamp(timestamp):.1f},{y_for_value(value):.1f}"
        for timestamp, value in points
    )
    last_timestamp, last_value = points[-1]
    last_x = x_for_timestamp(last_timestamp)
    last_y = y_for_value(last_value)
    return "".join(
        [
            f'<line x1="{x}" y1="{y + height:.1f}" x2="{x + width}" '
            f'y2="{y + height:.1f}" class="sparkline-baseline"/>',
            f'<polyline points="{coords}" fill="none" class="sparkline"/>',
            f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.5" class="sparkline-dot"/>',
        ]
    )


def _cash_fx_panel(
    retail_cash: dict,
    collected_at: datetime,
    cash_history: dict[str, list[tuple[datetime, float]]],
) -> str:
    y = 218
    height = 156
    quotes = retail_cash.get("quotes") or {}
    freshness = (
        f"Daily · collected {collected_at.strftime('%d %b %H:%M')} MMT"
        if quotes
        else "Daily · unavailable"
    )
    parts = [
        f'<rect x="32" y="{y}" width="1136" height="{height}" rx="12" class="panel"/>',
        _text(50, y + 31, "SuperRich Thailand cash FX", "panel-title"),
        _text(
            50,
            y + 53,
            "THB per foreign currency unit · buy price · 30-day sparkline",
            "panel-subtitle",
        ),
        _text(
            1150,
            y + 31,
            freshness,
            "freshness",
            "end",
        ),
    ]
    cell_width = 220
    for index, currency in enumerate(CASH_CURRENCIES):
        quote = quotes.get(currency) or {}
        x = 50 + index * cell_width
        if index:
            separator_x = x - 14
            parts.append(
                f'<line x1="{separator_x}" y1="{y + 68}" x2="{separator_x}" '
                f'y2="{y + 137}" class="grid"/>'
            )
        pair = str(quote.get("pair") or f"{currency}/THB").replace("/", " / ")
        buying = quote.get("buy_thb_per_unit")
        decimals = 4 if currency == "JPY" else 2
        parts.extend(
            [
                _text(x, y + 82, pair, "cash-pair"),
                _text(
                    x,
                    y + 111,
                    f"Buy {_number(buying, decimals)}",
                    "cash-value",
                ),
                _sparkline(cash_history.get(currency, []), x, y + 120, cell_width - 34, 28),
            ]
        )
    return "".join(parts)


def _trend_panel(
    x,
    width,
    title,
    subtitle,
    series: list[TrendSeries],
    reference: tuple[str, float, str] | None = None,
) -> str:
    y = TREND_Y
    height = TREND_HEIGHT
    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" class="panel"/>',
        _text(x + 18, y + 31, title, "panel-title"),
        _text(x + 18, y + 53, subtitle, "panel-subtitle"),
    ]
    point_count = max((len(item.points) for item in series), default=0)
    if 0 < point_count < MIN_TREND_POINTS:
        parts.append(
            _text(
                x + width - 18,
                y + 53,
                f"{point_count}/{MIN_TREND_POINTS} observations",
                "freshness",
                "end",
            )
        )
    if point_count == 0:
        parts.extend(
            [
                _text(x + width / 2, y + 176, "No trend observations", "empty-title", "middle"),
                _text(
                    x + width / 2,
                    y + 204,
                    "The trend will appear after the first observation",
                    "empty-note",
                    "middle",
                ),
            ]
        )
        return "".join(parts)

    all_points = [point for item in series for point in item.points]
    timestamps = [point[0] for point in all_points]
    values = [point[1] for point in all_points]
    if reference is not None:
        values.append(reference[1])
    min_time, max_time = min(timestamps), max(timestamps)
    min_value, max_value = min(values), max(values)
    if min_value == max_value:
        padding = abs(min_value) * 0.01 or 1
    else:
        padding = (max_value - min_value) * 0.12
    low, high = min_value - padding, max_value + padding

    plot_x = x + 52
    plot_y = y + 88
    plot_width = width - 72
    plot_height = height - 132

    def x_for_timestamp(timestamp):
        span = (max_time - min_time).total_seconds() or 1
        return plot_x + (timestamp - min_time).total_seconds() / span * plot_width

    def y_for_value(value):
        return plot_y + (high - value) / (high - low) * plot_height

    for ratio in (0, 0.5, 1):
        line_y = plot_y + ratio * plot_height
        parts.append(
            f'<line x1="{plot_x}" y1="{line_y:.1f}" x2="{plot_x + plot_width}" '
            f'y2="{line_y:.1f}" class="grid"/>'
        )
    parts.append(_text(plot_x - 8, plot_y + 4, _number(high), "axis", "end"))
    parts.append(_text(plot_x - 8, plot_y + plot_height + 4, _number(low), "axis", "end"))
    parts.append(_text(plot_x, plot_y + plot_height + 24, min_time.strftime("%d %b"), "axis"))
    parts.append(
        _text(
            plot_x + plot_width,
            plot_y + plot_height + 24,
            max_time.strftime("%d %b"),
            "axis",
            "end",
        )
    )

    if reference is not None:
        reference_y = y_for_value(reference[1])
        parts.append(
            f'<line x1="{plot_x}" y1="{reference_y:.1f}" x2="{plot_x + plot_width}" '
            f'y2="{reference_y:.1f}" stroke="{reference[2]}" stroke-width="1.5" '
            'stroke-dasharray="4 4"/>'
        )

    for series_index, item in enumerate(series):
        coords = " ".join(
            f"{x_for_timestamp(ts):.1f},{y_for_value(value):.1f}"
            for ts, value in item.points
        )
        dash_attr = f' stroke-dasharray="{item.dash}"' if item.dash else ""
        parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{item.color}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>'
        )
        last_ts, last_value = item.points[-1]
        parts.append(
            f'<circle cx="{x_for_timestamp(last_ts):.1f}" '
            f'cy="{y_for_value(last_value):.1f}" r="4" fill="{item.color}"/>'
        )
        if len(series) > 1 or reference is not None:
            legend_x = x + 18 + series_index * 126
            legend_y = y + 77
            parts.append(
                f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 22}" y2="{legend_y}" '
                f'stroke="{item.color}" stroke-width="2.5"{dash_attr}/>'
            )
            parts.append(_text(legend_x + 29, legend_y + 4, item.label, "legend"))
    if reference is not None:
        legend_x = x + 18 + len(series) * 126
        legend_y = y + 77
        parts.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 22}" y2="{legend_y}" '
            f'stroke="{reference[2]}" stroke-width="1.5" stroke-dasharray="4 4"/>'
        )
        parts.append(_text(legend_x + 29, legend_y + 4, reference[0], "legend"))
    return "".join(parts)


def generate_dashboard(data_dir: Path = DATA_DIR, output_path: Path = OUTPUT_PATH) -> Path:
    model = _load_dashboard_model(data_dir)
    latest = model.latest
    updated = model.updated
    market = model.market
    official = model.official
    retail_cash = model.retail_cash
    fuel = model.fuel
    fx_updated = model.fx_updated
    cash_updated = model.cash_updated
    fuel_updated = model.fuel_updated
    fx_history = model.fx_history
    fuel_history_points = model.fuel_history
    fuel_provenance = model.fuel_provenance

    updated_yangon = updated.astimezone(YANGON_TZ)
    status = "No source errors" if not latest.get("errors") else f"{len(latest['errors'])} source error(s)"
    svg = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img">',
        "<title>Myanmar market dashboard</title>",
        "<desc>Latest Myanmar P2P, official reference, SuperRich Thailand cash exchange, and fuel values with thirty-day trends.</desc>",
        """<style>
            text { font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; fill: #172033; }
            .panel { fill: #ffffff; stroke: #dbe3ef; stroke-width: 1; }
            .title { font-size: 25px; font-weight: 700; }
            .freshness { font-size: 12px; fill: #64748b; }
            .status { font-size: 12px; fill: #2563eb; font-weight: 600; }
            .card-label { font-size: 12px; fill: #64748b; font-weight: 600; }
            .card-value { font-size: 25px; font-weight: 700; }
            .card-note { font-size: 11px; fill: #64748b; }
            .cash-pair { font-size: 12px; fill: #64748b; font-weight: 650; }
            .cash-value { font-size: 17px; font-weight: 700; }
            .cash-note { font-size: 11px; fill: #64748b; }
            .sparkline { stroke: #2563eb; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
            .sparkline-dot { fill: #2563eb; }
            .sparkline-baseline { stroke: #dbe3ef; stroke-width: 1; }
            .cash-sparkline-empty { font-size: 12px; fill: #94a3b8; }
            .panel-title { font-size: 16px; font-weight: 700; }
            .panel-subtitle { font-size: 11px; fill: #64748b; }
            .empty-title { font-size: 16px; font-weight: 650; fill: #64748b; }
            .empty-note { font-size: 12px; fill: #94a3b8; }
            .axis { font-size: 10px; fill: #64748b; font-family: ui-monospace, SFMono-Regular, monospace; }
            .legend { font-size: 10px; fill: #64748b; }
            .grid { stroke: #dbe3ef; stroke-width: 1; }
            .footer { font-size: 11px; fill: #64748b; }
        </style>""",
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="16" fill="{BACKGROUND}"/>',
        _text(32, 46, "Myanmar market dashboard", "title"),
        _text(32, 67, status, "status"),
        _text(
            WIDTH - 32,
            46,
            f"Updated {updated_yangon.strftime('%d %b %Y, %H:%M')} MMT",
            "freshness",
            "end",
        ),
        _text(WIDTH - 32, 67, "30-day view · source-specific cadence", "freshness", "end"),
    ]

    cards = [
        (
            "USD / MMK",
            _number(market.get("USD_MMK")),
            f"P2P · {fx_updated.strftime('%d %b %H:%M')} MMT · 6 h",
            BLUE,
        ),
        (
            "THB / MMK",
            _number(market.get("THB_MMK"), 2),
            f"P2P · {fx_updated.strftime('%d %b %H:%M')} MMT · 6 h",
            BLUE,
        ),
        (
            "95 octane / L",
            _number(fuel.get("gasoline_95_mmk_per_litre_market")),
            f"Max median · {fuel_updated.strftime('%d %b')} · daily",
            ORANGE,
        ),
        (
            "Diesel / L",
            _number(fuel.get("diesel_mmk_per_litre_market")),
            f"Max median · {fuel_updated.strftime('%d %b')} · daily",
            BLUE,
        ),
    ]
    for index, card in enumerate(cards):
        svg.append(_card(32 + index * 288, 272, *card))

    svg.append(_cash_fx_panel(retail_cash, cash_updated, model.cash_history))

    official_mmk = official.get("USD_MMK")
    fx_subtitle = "Last 30 days · P2P market with CBM reference · MMK per USD"
    if len(fx_history) < MIN_TREND_POINTS:
        fx_subtitle += f" · {len(fx_history)} observation{'' if len(fx_history) == 1 else 's'}"
    svg.append(
        _trend_panel(
            32,
            560,
            "Market USD / MMK trend",
            fx_subtitle,
            [
                TrendSeries(
                    "P2P market",
                    [(ts, values[0]) for ts, values in fx_history],
                    BLUE,
                )
            ],
            reference=("CBM official", float(official_mmk), TEAL)
            if official_mmk is not None
            else None,
        )
    )
    svg.append(
        _trend_panel(
            608,
            560,
            "Fuel / litre",
            (
                f"Last 30 days · {fuel_provenance['backfill']} backfill + "
                f"{fuel_provenance['scheduled']} scheduled · station median MMK"
            ),
            [
                TrendSeries(
                    "95 octane",
                    [(ts, values[0]) for ts, values in fuel_history_points],
                    ORANGE,
                ),
                TrendSeries(
                    "Diesel",
                    [(ts, values[1]) for ts, values in fuel_history_points],
                    BLUE,
                    "6 4",
                ),
            ],
        )
    )
    svg.extend(
        [
            _text(
                32,
                810,
                "Sources: P2P market rates · SuperRich Thailand · Max Energy Myanmar",
                "footer",
            ),
            _text(
                WIDTH - 32,
                810,
                "Generated from committed JSON and CSV history",
                "footer",
                "end",
            ),
            "</svg>",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text("".join(svg) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return output_path


if __name__ == "__main__":
    generated = generate_dashboard()
    print(f"wrote {generated}")
