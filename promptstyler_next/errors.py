"""Errors shared by every integration boundary."""

from __future__ import annotations


class StylerError(ValueError):
    """A stable, machine-readable domain failure; messages never include input payloads."""

    def __init__(self, code: str, message: str, path: str = "") -> None:
        self.code = code
        self.message = message
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.path}
