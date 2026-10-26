"""Stable machine-readable errors shared across the process boundary."""


class CADException(ValueError):
    """An expected validation or modelling failure, safe to show to the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self)}
