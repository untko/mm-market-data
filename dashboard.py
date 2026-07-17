#!/usr/bin/env python3
"""Generate the static SVG dashboard embedded in the repository README."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_PATH = ROOT / "dashboard" / "market-trends.svg"

WIDTH = 1200
HEIGHT = 650
MIN_TREND_POINTS = 8
YANGON_TZ = timezone(timedelta(hours=6, minutes=30))

INK = "#172033"
MUTED = "#64748b"
GRID = "#dbe3ef"
PANEL = "#ffffff"
BACKGROUND = "#f6f8fc"
BLUE = "#2563eb"
ORANGE = "#e87817"


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


def _trend_panel(x, width, title, subtitle, series) -> str:
    y = 218
    height = 352
    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" class="panel"/>',
        _text(x + 18, y + 31, title, "panel-title"),
        _text(x + 18, y + 53, subtitle, "panel-subtitle"),
    ]
    point_count = max((len(points) for _, points, _, _ in series), default=0)
    if point_count < MIN_TREND_POINTS:
        parts.extend(
            [
                _text(x + width / 2, y + 176, "Collecting history", "empty-title", "middle"),
                _text(
                    x + width / 2,
                    y + 204,
                    f"Collecting history · {point_count}/{MIN_TREND_POINTS} points",
                    "empty-note",
                    "middle",
                ),
                _text(
                    x + width / 2,
                    y + 229,
                    "Trend appears after enough observations",
                    "empty-note",
                    "middle",
                ),
            ]
        )
        return "".join(parts)

    all_points = [point for _, points, _, _ in series for point in points]
    timestamps = [point[0] for point in all_points]
    values = [point[1] for point in all_points]
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

    def sx(timestamp):
        span = (max_time - min_time).total_seconds() or 1
        return plot_x + (timestamp - min_time).total_seconds() / span * plot_width

    def sy(value):
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

    for series_index, (label, points, color, dash) in enumerate(series):
        coords = " ".join(f"{sx(ts):.1f},{sy(value):.1f}" for ts, value in points)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>'
        )
        last_ts, last_value = points[-1]
        parts.append(f'<circle cx="{sx(last_ts):.1f}" cy="{sy(last_value):.1f}" r="4" fill="{color}"/>')
        if len(series) > 1:
            legend_x = x + 18 + series_index * 126
            legend_y = y + 77
            parts.append(
                f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 22}" y2="{legend_y}" '
                f'stroke="{color}" stroke-width="2.5"{dash_attr}/>'
            )
            parts.append(_text(legend_x + 29, legend_y + 4, label, "legend"))
    return "".join(parts)


def generate_dashboard(data_dir: Path = DATA_DIR, output_path: Path = OUTPUT_PATH) -> Path:
    latest = json.loads((data_dir / "latest.json").read_text(encoding="utf-8"))
    updated = datetime.fromisoformat(latest["updated_at_utc"])
    fx = latest.get("fx") or {}
    market = fx.get("market") or {}
    fuel = latest.get("fuel") or {}

    def snapshot_updated(filename: str) -> datetime:
        path = data_dir / filename
        if not path.exists():
            return updated
        try:
            return datetime.fromisoformat(json.loads(path.read_text())["updated_at_utc"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return updated

    fx_updated = snapshot_updated("exchange_rates.json").astimezone(YANGON_TZ)
    fuel_updated = snapshot_updated("fuel.json").astimezone(YANGON_TZ)

    fx_history = _window(
        _read_history(data_dir / "history" / "exchange_rates.csv", ["usd_mmk_market"]), updated
    )
    fuel_history = []
    fuel_path = data_dir / "history" / "fuel.csv"
    if fuel_path.exists():
        with fuel_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    # Max Energy observations use ISO source dates. This excludes
                    # the older GlobalPetrolPrices row without conflating sources.
                    datetime.fromisoformat(row["as_of"])
                    source_date = datetime.fromisoformat(row["as_of"]).date()
                    timestamp = datetime.combine(
                        source_date, datetime.min.time(), tzinfo=YANGON_TZ
                    )
                    values = [
                        float(row["gasoline_95_mmk_per_litre_market"]),
                        float(row["diesel_mmk_per_litre_market"]),
                    ]
                except (KeyError, TypeError, ValueError):
                    continue
                fuel_history.append((timestamp, values))
    fuel_history = _window(fuel_history, updated)

    updated_yangon = updated.astimezone(YANGON_TZ)
    status = "No source errors" if not latest.get("errors") else f"{len(latest['errors'])} source error(s)"
    svg = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img">',
        "<title>Myanmar market dashboard</title>",
        "<desc>Latest Myanmar market exchange and fuel values with thirty-day trends.</desc>",
        """<style>
            text { font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; fill: #172033; }
            .panel { fill: #ffffff; stroke: #dbe3ef; stroke-width: 1; }
            .title { font-size: 25px; font-weight: 700; }
            .freshness { font-size: 12px; fill: #64748b; }
            .status { font-size: 12px; fill: #2563eb; font-weight: 600; }
            .card-label { font-size: 12px; fill: #64748b; font-weight: 600; }
            .card-value { font-size: 25px; font-weight: 700; }
            .card-note { font-size: 11px; fill: #64748b; }
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

    svg.append(
        _trend_panel(
            32,
            560,
            "Market USD / MMK",
            "Last 30 days · focused scale · MMK per USD",
            [("USD / MMK", [(ts, values[0]) for ts, values in fx_history], BLUE, None)],
        )
    )
    svg.append(
        _trend_panel(
            608,
            560,
            "Fuel / litre",
            "Last 30 days · focused scale · station median MMK",
            [
                ("95 octane", [(ts, values[0]) for ts, values in fuel_history], ORANGE, None),
                ("Diesel", [(ts, values[1]) for ts, values in fuel_history], BLUE, "6 4"),
            ],
        )
    )
    svg.extend(
        [
            _text(
                32,
                620,
                "Sources: P2P market rates · Max Energy Myanmar",
                "footer",
            ),
            _text(
                WIDTH - 32,
                620,
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
