from os import getenv

import httpx


ACCOUNT_ID = "default"


class PortfolioStoreError(Exception):
    """Raised when the private portfolio store cannot be reached."""


def _request(method: str, table: str, **kwargs) -> list[dict]:
    url = getenv("SUPABASE_URL")
    secret = getenv("SUPABASE_SECRET_KEY") or getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not secret:
        raise PortfolioStoreError("Supabase credentials are not configured")
    response = httpx.request(
        method,
        f"{url.rstrip('/')}/rest/v1/{table}",
        headers={
            "apikey": secret,
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        },
        timeout=10.0,
        **kwargs,
    )
    if not response.is_success:
        raise PortfolioStoreError(f"Supabase returned HTTP {response.status_code}")
    return response.json() if response.content else []


def get_portfolio_summary() -> dict:
    accounts = _request(
        "GET", "portfolio_accounts", params={"id": f"eq.{ACCOUNT_ID}", "select": "*", "limit": 1}
    )
    account = accounts[0] if accounts else None
    positions = _request(
        "GET", "positions", params={"account_id": f"eq.{ACCOUNT_ID}", "select": "*", "order": "ticker.asc"}
    )
    available_cash = float(account["available_cash"]) if account else 0.0
    account_value = float(account["account_value"]) if account else 0.0
    allocated_cash = max(account_value - available_cash, 0.0)
    planned_risk = sum(float(position.get("planned_risk", 0) or 0) for position in positions)
    return {
        "account": account,
        "positions": positions,
        "account_value": account_value,
        "available_cash": available_cash,
        "allocated_cash": allocated_cash,
        "open_positions": len(positions),
        "planned_risk": planned_risk,
    }


def save_account(payload: dict) -> dict:
    rows = _request(
        "POST",
        "portfolio_accounts",
        params={"on_conflict": "id"},
        json={"id": ACCOUNT_ID, **payload},
    )
    return rows[0] if rows else {"id": ACCOUNT_ID, **payload}
