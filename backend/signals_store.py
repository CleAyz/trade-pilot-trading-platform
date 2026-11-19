"""Supabase persistence for scanner history and the manual research watchlist."""

from __future__ import annotations

from datetime import UTC, datetime
from os import getenv
from typing import Any

import httpx


class SignalStoreError(RuntimeError):
    """Raised when the Supabase signal store cannot be reached."""


def _request(method: str, table: str, **kwargs: Any) -> list[dict]:
    url = getenv("SUPABASE_URL")
    secret = getenv("SUPABASE_SECRET_KEY") or getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not secret:
        raise SignalStoreError("Supabase credentials are not configured")
    response = httpx.request(
        method,
        f"{url.rstrip('/')}/rest/v1/{table}",
        headers={
            "apikey": secret,
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        },
        timeout=15.0,
        **kwargs,
    )
    if not response.is_success:
        if response.status_code == 404 and table in {"signal_history", "watchlist_items"}:
            raise SignalStoreError(
                f"Supabase table '{table}' is missing. Apply "
                "supabase/migrations/0003_signal_history_watchlist.sql in the Supabase SQL Editor."
            )
        raise SignalStoreError(f"Supabase returned HTTP {response.status_code}")
    return response.json() if response.content else []


def save_scan(signals: list[dict[str, Any]], scanned_at: datetime) -> list[dict]:
    rows = []
    for signal in signals:
        rows.append({
            "fingerprint": "|".join(str(signal.get(key, "")) for key in (
                "ticker", "setup", "signal_date", "entry_price", "stop_loss", "target_price"
            )),
            "ticker": signal["ticker"], "setup": signal["setup"], "score": signal["score"],
            "price": signal["price"], "entry_price": signal["entry_price"],
            "stop_loss": signal["stop_loss"], "target_price": signal["target_price"],
            "risk_reward": signal["risk_reward"], "explanation": signal["explanation"],
            "relative_volume": signal.get("relative_volume", 0), "source": signal.get("source", "unknown"),
            "signal_date": signal.get("signal_date"), "scanned_at": scanned_at.isoformat(),
        })
    if not rows:
        return []
    return _request("POST", "signal_history", params={"on_conflict": "fingerprint"}, json=rows)


def list_history(unread_only: bool = False, limit: int = 100) -> list[dict]:
    params: dict[str, str] = {"select": "*", "order": "scanned_at.desc", "limit": str(min(max(limit, 1), 200))}
    if unread_only:
        params["reviewed_at"] = "is.null"
    return _request("GET", "signal_history", params=params)


def mark_reviewed(signal_id: str) -> dict:
    rows = _request("PATCH", "signal_history", params={"id": f"eq.{signal_id}"}, json={"reviewed_at": datetime.now(UTC).isoformat()})
    if not rows:
        raise SignalStoreError("Signal was not found")
    return rows[0]


def list_watchlist() -> list[dict]:
    return _request("GET", "watchlist_items", params={"select": "*", "order": "updated_at.desc"})


def add_watchlist(ticker: str, notes: str = "", status: str = "watching", signal_id: str | None = None) -> dict:
    rows = _request("POST", "watchlist_items", params={"on_conflict": "ticker"}, json={
        "ticker": ticker.upper().strip(), "notes": notes, "status": status, "signal_id": signal_id,
    })
    return rows[0] if rows else {}


def update_watchlist(item_id: str, payload: dict[str, Any]) -> dict:
    rows = _request("PATCH", "watchlist_items", params={"id": f"eq.{item_id}"}, json={**payload, "updated_at": datetime.now(UTC).isoformat()})
    if not rows:
        raise SignalStoreError("Watchlist item was not found")
    return rows[0]


def delete_watchlist(item_id: str) -> None:
    _request("DELETE", "watchlist_items", params={"id": f"eq.{item_id}"})
