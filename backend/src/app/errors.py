from enum import StrEnum


class LiveRetryDisposition(StrEnum):
    """Exclusive live-provider retry classification.

    SAFE_RETRY is the only disposition that may repeat an external request.
    """

    SAFE_RETRY = "safe_retry"
    AMBIGUOUS = "ambiguous"
    TERMINAL = "terminal"


class Phase02Error(Exception):
    def __init__(self, code: str, detail: str, action: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.action = action


class NotFoundError(Phase02Error):
    pass


class ValidationError(Phase02Error):
    pass


class StorageError(Phase02Error):
    pass


class ParserError(Phase02Error):
    pass


class ProvenanceError(Phase02Error):
    pass


class ModelError(Phase02Error):
    def __init__(
        self,
        code: str,
        detail: str,
        action: str,
        *,
        retryable: bool = False,
        retry_disposition: LiveRetryDisposition | None = None,
        attempt_count: int | None = None,
    ) -> None:
        super().__init__(code, detail, action)
        if retry_disposition is None:
            self.retry_disposition = LiveRetryDisposition.TERMINAL
            self.retryable = retryable
        else:
            self.retry_disposition = retry_disposition
            self.retryable = retry_disposition is LiveRetryDisposition.SAFE_RETRY
        self.attempt_count = attempt_count
