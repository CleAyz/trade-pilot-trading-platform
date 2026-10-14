from datetime import UTC, datetime
from os import getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    demo_mode: bool
    data_provider: str
    checked_at: datetime


app = FastAPI(
    title="TradePilot API",
    version="0.1.0",
    description="Private server-side API foundation for the TradePilot trading workspace.",
)

# Keep this narrow for local development. Production origins should be set explicitly
# when the frontend and API are deployed behind access controls.
frontend_origin = getenv("TRADEPILOT_FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Report API availability without exposing credentials or provider secrets."""
    provider = getenv("TRADEPILOT_MARKET_DATA_PROVIDER", "not_configured")
    return HealthResponse(
        status="ok",
        service="tradepilot-api",
        demo_mode=provider == "not_configured",
        data_provider=provider,
        checked_at=datetime.now(UTC),
    )
