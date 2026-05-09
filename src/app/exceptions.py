from fastapi import Request
from fastapi.responses import JSONResponse


class QueueOverloadError(Exception):
    """Raised when the concurrency queue is full."""


async def queue_overload_handler(request: Request, exc: QueueOverloadError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "5"},
        content={"detail": "Server at capacity. Try again shortly."},
    )
