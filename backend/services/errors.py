"""Typed service errors → the {success: false, error: {code, message}} response contract."""

from __future__ import annotations

from ml.imaging import ImageValidationError


class MlServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    @classmethod
    def from_validation(cls, exc: ImageValidationError) -> "MlServiceError":
        return cls(exc.code, exc.message, exc.status_code)


MODEL_NOT_LOADED_MESSAGES = {
    "identification": "Identification model is not available.",
    "classification": "Classification model is not available.",
    "prediction": "Prediction model is not available.",
}
