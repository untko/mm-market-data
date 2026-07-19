"""Shared helpers: HTTP, JSON/CSV output, timestamps."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone, timedelta

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 25

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def get_json(url: str, **kwargs):
    headers = {**UA, **kwargs.pop("headers", {})}
    resp = requests.get(url, headers=headers, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp.json()


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def yangon_now() -> str:
    tz = timezone(timedelta(hours=6, minutes=30))
    return datetime.now(tz).replace(microsecond=0).isoformat()


def write_json(relpath: str, obj) -> None:
    path = os.path.join(DATA_DIR, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def read_json(relpath: str):
    path = os.path.join(DATA_DIR, relpath)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def append_csv(relpath: str, row: dict, dedupe_keys) -> bool:
    """Append a row; skip if the last row matches on dedupe_keys. Returns True if appended."""
    path = os.path.join(DATA_DIR, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exists = os.path.exists(path)
    if exists:
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            last = rows[-1]
            if all(str(last.get(k, "")) == str(row.get(k, "")) for k in dedupe_keys):
                return False
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    return True
