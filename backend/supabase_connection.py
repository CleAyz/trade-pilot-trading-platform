from os import getenv

import httpx


def check_supabase_connection() -> tuple[bool, str]:
    """Check the Supabase REST gateway without logging the server-only key."""
    url = getenv("SUPABASE_URL")
    secret_key = getenv("SUPABASE_SECRET_KEY") or getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not secret_key:
        return False, "not_configured"

    try:
        response = httpx.get(
            f"{url.rstrip('/')}/rest/v1/",
            headers={"apikey": secret_key, "Authorization": f"Bearer {secret_key}"},
            timeout=5.0,
        )
        if response.is_success:
            return True, "reachable"
        return False, f"http_{response.status_code}"
    except httpx.HTTPError:
        return False, "unreachable"
