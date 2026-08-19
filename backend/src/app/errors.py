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
