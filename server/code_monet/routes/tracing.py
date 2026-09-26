"""Client tracing endpoints for distributed tracing."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from code_monet.auth.rate_limit import TRACES_BY_IP, rate_limiter
from code_monet.tracing import record_client_spans

router = APIRouter()


class ClientSpan(BaseModel):
    """A span from the mobile/web client."""

    traceId: str
    spanId: str
    parentSpanId: str | None = None
    name: str
    startTime: int  # Unix timestamp in ms
    endTime: int | None = None
    attributes: dict[str, str | int | float | bool] = {}
    status: str = "ok"
    error: str | None = None

    @field_validator("startTime", "endTime", mode="before")
    @classmethod
    def _truncate_to_millis(cls, value: float | int | None) -> int | None:
        """Clients (Swift's `Date().timeIntervalSince1970 * 1000`, in
        particular) send sub-millisecond-precision floats; truncate rather
        than reject them (was a hard `int` field, so every flush from the
        iOS client 422'd)."""
        if value is None:
            return None
        return int(value)


class TracesRequest(BaseModel):
    """Request body for POST /traces."""

    spans: list[ClientSpan]


@router.post("/traces")
async def receive_traces(traces_request: TracesRequest, request: Request) -> dict[str, int]:
    """Receive traces from mobile/web clients.

    Accepts spans from client-side tracing and forwards them to X-Ray
    via the OpenTelemetry collector. This enables end-to-end distributed
    tracing from mobile app through the server.

    No authentication required to minimize overhead on the client.
    Spans are tagged with client.source=mobile for filtering.
    Rate limited to 60 requests/minute per IP.
    """
    # Rate limit by IP (check X-Forwarded-For for clients behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    client_ip = forwarded_for or (request.client.host if request.client else "unknown")
    if not rate_limiter.is_allowed(f"traces:{client_ip}", TRACES_BY_IP):
        raise HTTPException(status_code=429, detail="Too many requests")

    # Convert Pydantic models to dicts for the tracing function
    spans_data = [span.model_dump() for span in traces_request.spans]
    recorded = record_client_spans(spans_data)
    return {"received": recorded}
