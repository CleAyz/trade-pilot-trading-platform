"""Signal persistence and optional Telegram delivery for TradePilot alerts."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx


class AlertDeliveryError(RuntimeError):
    """Raised when a configured alert channel cannot deliver a message."""


def _cache_path() -> Path:
    return Path(os.getenv("TRADEPILOT_CACHE_PATH", "work/market_data.sqlite3"))


def signal_fingerprint(signal: dict[str, Any]) -> str:
    """Return a stable key so the same ticker/setup/day alerts only once."""
    raw = "|".join(
        str(signal.get(field, ""))
        for field in ("ticker", "setup", "signal_date", "entry_price", "stop_loss", "target_price")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AlertStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path) if path else _cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                create table if not exists signal_alerts (
                    fingerprint text primary key,
                    ticker text not null,
                    setup text not null,
                    signal_date text not null,
                    score real not null,
                    entry_price real not null,
                    stop_loss real not null,
                    target_price real not null,
                    risk_reward real not null,
                    explanation text not null,
                    source text not null,
                    first_seen_at text not null,
                    notified_at text,
                    last_error text
                )
                """
            )

    def register(self, signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        new_signals: list[dict[str, Any]] = []
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.path) as connection:
            for signal in signals:
                fingerprint = signal_fingerprint(signal)
                cursor = connection.execute(
                    """
                    insert or ignore into signal_alerts
                        (fingerprint, ticker, setup, signal_date, score, entry_price,
                         stop_loss, target_price, risk_reward, explanation, source, first_seen_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fingerprint,
                        signal["ticker"],
                        signal["setup"],
                        signal.get("signal_date", "unknown"),
                        float(signal["score"]),
                        float(signal["entry_price"]),
                        float(signal["stop_loss"]),
                        float(signal["target_price"]),
                        float(signal["risk_reward"]),
                        signal["explanation"],
                        signal.get("source", "unknown"),
                        now,
                    ),
                )
                if cursor.rowcount:
                    new_signals.append({**signal, "fingerprint": fingerprint})
        return new_signals

    def pending(self, fingerprints: list[str] | None = None) -> list[dict[str, Any]]:
        filters = ["notified_at is null"]
        params: list[Any] = []
        if fingerprints:
            placeholders = ",".join("?" for _ in fingerprints)
            filters.append(f"fingerprint in ({placeholders})")
            params.extend(fingerprints)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                f"select fingerprint, ticker, setup, signal_date, score, entry_price, stop_loss, "
                f"target_price, risk_reward, explanation, source from signal_alerts "
                f"where {' and '.join(filters)} order by first_seen_at asc",
                params,
            ).fetchall()
        fields = (
            "fingerprint", "ticker", "setup", "signal_date", "score", "entry_price",
            "stop_loss", "target_price", "risk_reward", "explanation", "source",
        )
        return [dict(zip(fields, row)) for row in rows]

    def mark_notified(self, fingerprint: str) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "update signal_alerts set notified_at = ?, last_error = null where fingerprint = ?",
                (datetime.now(UTC).isoformat(), fingerprint),
            )

    def mark_error(self, fingerprint: str, error: str) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "update signal_alerts set last_error = ? where fingerprint = ?",
                (error[:500], fingerprint),
            )

    def counts(self) -> dict[str, int]:
        with sqlite3.connect(self.path) as connection:
            total, notified, pending = connection.execute(
                "select count(*), count(notified_at), count(*) - count(notified_at) from signal_alerts"
            ).fetchone()
        return {"total": total, "notified": notified, "pending": pending}


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.getenv("TRADEPILOT_TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.getenv("TRADEPILOT_TELEGRAM_CHAT_ID", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, signal: dict[str, Any]) -> None:
        if not self.configured:
            raise AlertDeliveryError(
                "Telegram is not configured. Set TRADEPILOT_TELEGRAM_BOT_TOKEN and "
                "TRADEPILOT_TELEGRAM_CHAT_ID."
            )
        message = (
            f"TradePilot signal · {signal['ticker']}\n"
            f"Setup: {signal['setup']}\n"
            f"Score: {float(signal['score']):.0f}/100\n"
            f"Entry: ${float(signal['entry_price']):.2f}\n"
            f"Stop: ${float(signal['stop_loss']):.2f}\n"
            f"Target: ${float(signal['target_price']):.2f}\n"
            f"R:R: {float(signal['risk_reward']):.1f}R\n"
            f"Why: {signal['explanation']}\n"
            "Research alert only — review before manually executing in IBKR."
        )
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            response = httpx.post(url, json={"chat_id": self.chat_id, "text": message}, timeout=15)
            response.raise_for_status()
            body = response.json()
            if not body.get("ok"):
                raise AlertDeliveryError(f"Telegram rejected the message: {json.dumps(body)[:300]}")
        except (httpx.HTTPError, ValueError) as exc:
            raise AlertDeliveryError(f"Telegram delivery failed: {exc}") from exc


class AlertService:
    def __init__(self, store: AlertStore | None = None, notifier: TelegramNotifier | None = None) -> None:
        self.store = store or AlertStore()
        self.notifier = notifier or TelegramNotifier()

    def process(self, signals: list[dict[str, Any]]) -> dict[str, Any]:
        new_signals = self.store.register(signals)
        # Retry any previously stored but undelivered signals after configuration or outages.
        pending = self.store.pending()
        sent = 0
        errors: list[str] = []
        for signal in pending:
            try:
                self.notifier.send(signal)
                self.store.mark_notified(signal["fingerprint"])
                sent += 1
            except AlertDeliveryError as exc:
                self.store.mark_error(signal["fingerprint"], str(exc))
                errors.append(str(exc))
        return {
            "signals_found": len(signals),
            "new_signals": len(new_signals),
            "alerts_sent": sent,
            "pending": self.store.counts()["pending"],
            "errors": errors,
        }
