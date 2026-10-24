from os import getenv


class IBKRConnectionError(Exception):
    """Raised when the local IBKR TWS or Gateway cannot be reached."""


def _number(values: list, tag: str) -> float:
    matches = [value for value in values if value.tag == tag and value.currency in {"BASE", ""}]
    if not matches:
        matches = [value for value in values if value.tag == tag]
    try:
        return float(matches[0].value) if matches else 0.0
    except (TypeError, ValueError):
        return 0.0


def read_ibkr_portfolio() -> dict:
    try:
        from ib_insync import IB
    except ImportError as exc:
        raise IBKRConnectionError("IBKR support is not installed. Run pip install -r backend/requirements.txt") from exc

    host = getenv("IBKR_HOST", "127.0.0.1")
    port = int(getenv("IBKR_PORT", "7497"))
    client_id = int(getenv("IBKR_CLIENT_ID", "17"))
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=5, readonly=True)
        accounts = ib.managedAccounts()
        if not accounts:
            raise IBKRConnectionError("IBKR connected, but no managed account was returned")
        account_id = accounts[0]
        values = ib.accountSummary(account_id)
        positions = [
            {
                "ticker": position.contract.symbol,
                "quantity": float(position.position),
                "average_price": float(position.avgCost),
                "currency": position.contract.currency or "USD",
                "planned_risk": 0.0,
                "style": "swing",
            }
            for position in ib.positions(account_id)
            if float(position.position) != 0
        ]
        return {
            "account_id": account_id,
            "base_currency": getenv("IBKR_BASE_CURRENCY", "SGD"),
            "account_value": _number(values, "NetLiquidation"),
            "available_cash": _number(values, "AvailableFunds"),
            "positions": positions,
            "source": "ibkr_tws_read_only",
        }
    except IBKRConnectionError:
        raise
    except Exception as exc:
        raise IBKRConnectionError(f"Could not read IBKR portfolio: {exc}") from exc
    finally:
        if ib.isConnected():
            ib.disconnect()
