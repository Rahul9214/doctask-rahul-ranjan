from collections.abc import Awaitable, Callable

from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

MULTIPART_OVERHEAD_BYTES = 1024 * 1024
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class UploadRequestSizeGuard:
    """Reject clearly oversized multipart requests before route parsing."""

    def __init__(self, app: ASGIApp, *, max_upload_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_upload_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _is_source_upload(scope):
            content_length = _content_length(scope)
            if content_length is not None and content_length > self.max_request_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "code": "request_too_large",
                        "detail": "The upload request exceeds the configured HTTP request bound.",
                        "action": (
                            "Reduce multipart request size or increase MAX_UPLOAD_BYTES "
                            "deliberately."
                        ),
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _is_source_upload(scope: Scope) -> bool:
    if scope.get("method") != "POST":
        return False
    parts = scope.get("path", "").strip("/").split("/")
    return len(parts) == 3 and parts[0] == "corpora" and parts[2] == "sources"


def _content_length(scope: Scope) -> int | None:
    headers = dict(scope.get("headers", []))
    raw_value = headers.get(b"content-length")
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        return None
    return value if value >= 0 else None
