from backend.alerts import AlertService, AlertStore, TelegramNotifier, signal_fingerprint


def sample_signal():
    return {
        "ticker": "AAPL",
        "setup": "Momentum Breakout",
        "score": 88,
        "price": 200.0,
        "relative_volume": 1.6,
        "entry_price": 200.0,
        "stop_loss": 194.0,
        "target_price": 212.0,
        "risk_reward": 2.0,
        "explanation": "Trend and breakout confirmed.",
        "signal_date": "2026-11-18",
        "source": "test",
    }


def test_signal_fingerprint_is_stable():
    assert signal_fingerprint(sample_signal()) == signal_fingerprint(sample_signal())


def test_alert_store_registers_a_signal_only_once(tmp_path):
    store = AlertStore(str(tmp_path / "alerts.sqlite3"))
    signal = sample_signal()

    assert len(store.register([signal])) == 1
    assert store.register([signal]) == []
    assert store.counts() == {"total": 1, "notified": 0, "pending": 1}


def test_alert_service_reports_missing_telegram_configuration(tmp_path):
    store = AlertStore(str(tmp_path / "alerts.sqlite3"))
    service = AlertService(store=store, notifier=TelegramNotifier(token="", chat_id=""))

    result = service.process([sample_signal()])

    assert result["new_signals"] == 1
    assert result["alerts_sent"] == 0
    assert result["pending"] == 1
    assert "Telegram is not configured" in result["errors"][0]


def test_alert_service_retries_pending_signal(tmp_path):
    store = AlertStore(str(tmp_path / "alerts.sqlite3"))
    unavailable = AlertService(store=store, notifier=TelegramNotifier(token="", chat_id=""))
    unavailable.process([sample_signal()])

    delivered = []

    class FakeNotifier:
        configured = True

        def send(self, signal):
            delivered.append(signal["ticker"])

    retry = AlertService(store=store, notifier=FakeNotifier())
    result = retry.process([])

    assert delivered == ["AAPL"]
    assert result["alerts_sent"] == 1
    assert result["pending"] == 0
