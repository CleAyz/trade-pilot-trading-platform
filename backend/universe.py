"""Free, cached community index lists for personal research scans."""
import csv
import io
import json
import re
import time
from pathlib import Path

import httpx

SOURCES = {
    "sp500": ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv", "Symbol"),
    "nasdaq100": ("https://raw.githubusercontent.com/Gary-Strauss/NASDAQ100_Constituents/master/data/nasdaq100_constituents.csv", "Ticker"),
}
CACHE = Path("work/universe.json")


def get_universe(name: str) -> list[str]:
    if name not in (*SOURCES, "combined"):
        raise ValueError("Unknown universe")
    try:
        saved = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    except (ValueError, OSError):
        saved = {}
    result: dict[str, list[str]] = {}
    for key in (SOURCES if name == "combined" else (name,)):
        url, column = SOURCES[key]
        entry = saved.get(key, {})
        if time.time() - entry.get("time", 0) < 86400 and entry.get("symbols"):
            result[key] = entry["symbols"]
            continue
        try:
            response = httpx.get(url, timeout=15)
            response.raise_for_status()
            symbols = [row[column].strip().upper().replace(".", "-") for row in csv.DictReader(io.StringIO(response.text))]
            symbols = sorted({s for s in symbols if re.fullmatch(r"[A-Z][A-Z0-9-]{0,9}", s)})
            if not 80 <= len(symbols) <= 600:
                raise ValueError("Index list size is unexpected")
            result[key] = symbols
            saved[key] = {"time": time.time(), "symbols": symbols}
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            if entry.get("symbols"):
                result[key] = entry["symbols"]
            else:
                raise ValueError(f"Could not load {key} ticker list: {exc}") from exc
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(saved))
    return sorted(set().union(*result.values()))
