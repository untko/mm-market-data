"""Fuel: Myanmar pump prices (gasoline 95 & diesel, USD/litre) scraped from
GlobalPetrolPrices.com country chart. The chart is JS-rendered, so this uses
headless Chromium via Playwright. GPP updates weekly (Mondays)."""
from __future__ import annotations

import re
import shutil

GASOLINE_URL = "https://www.globalpetrolprices.com/gasoline_prices/"
DIESEL_URL = "https://www.globalpetrolprices.com/diesel_prices/"
COUNTRY = "Burma"  # label used by GlobalPetrolPrices

_EXTRACT_JS = """(country) => {
    const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
    const valRe = /^\\d+\\.\\d{2,3}$/;
    const names = [...document.querySelectorAll('.outsideTitleElement, .outsideTitle')]
        .map(e => clean(e.textContent)).filter(t => t);
    const vals = [...document.querySelectorAll('body *')]
        .filter(e => e.children.length === 0 && e.offsetParent !== null && valRe.test(clean(e.textContent)))
        .map(e => parseFloat(clean(e.textContent)));
    let v = vals.slice();
    if (v.length === names.length + 1) {
        // one extra value (world average) — find the removal that restores the
        // chart's ascending order
        for (let i = 0; i < v.length; i++) {
            const t = v.slice(0, i).concat(v.slice(i + 1));
            let mono = true;
            for (let j = 1; j < t.length; j++) if (t[j] < t[j - 1]) { mono = false; break; }
            if (mono) { v = t; break; }
        }
    }
    if (v.length !== names.length) return { error: `misaligned: ${names.length} names vs ${v.length} values` };
    const idx = names.findIndex(t => t === country || t === country + '*');
    if (idx < 0) return { error: 'country not found in chart' };
    const m = document.title.match(/(\\d{2}-\\w{3}-\\d{4})/);
    return { price: v[idx], as_of: m ? m[1] : null };
}"""

_WAIT_JS = """() => document.querySelectorAll('.outsideTitleElement, .outsideTitle').length > 100"""


def _launch_browser(p):
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    exe = shutil.which("chromium") or shutil.which("chromium-browser")
    kwargs = {"args": args, "headless": True}
    if exe:  # local dev: use system chromium; CI uses playwright's own build
        kwargs["executable_path"] = exe
    return p.chromium.launch(**kwargs)


def _scrape_one(p, url: str) -> dict:
    browser = _launch_browser(p)
    try:
        page = browser.new_page(user_agent=common_ua())
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function(_WAIT_JS, timeout=45000)
        result = page.evaluate(_EXTRACT_JS, COUNTRY)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result
    finally:
        browser.close()


def common_ua() -> str:
    from . import common

    return common.UA["User-Agent"]


def fetch(usd_mmk_market: float | None = None) -> dict:
    errors = []
    fuel = None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            gasoline = _scrape_one(p, GASOLINE_URL)
            diesel = _scrape_one(p, DIESEL_URL)
        fuel = {
            "gasoline_95_usd_per_litre": gasoline["price"],
            "diesel_usd_per_litre": diesel["price"],
            "as_of": gasoline["as_of"] or diesel["as_of"],
            "source": "GlobalPetrolPrices.com (weekly, octane-95 gasoline & diesel)",
        }
        if usd_mmk_market:
            fuel["gasoline_95_mmk_per_litre_market"] = round(gasoline["price"] * usd_mmk_market, 2)
            fuel["diesel_mmk_per_litre_market"] = round(diesel["price"] * usd_mmk_market, 2)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"fuel_gpp: {exc}")
    return {"data": fuel, "errors": errors}
