"""Domain errors. The API layer maps each one to an HTTP status code."""
from __future__ import annotations


class FleetError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidRequest(FleetError):
    """The request is well-formed JSON but breaks a business rule (HTTP 400)."""
    status_code = 400


class NotFound(FleetError):
    status_code = 404


class Conflict(FleetError):
    """The requested change conflicts with the current state (HTTP 409)."""
    status_code = 409


class ModelUnavailable(FleetError):
    """The TensorFlow model is not loaded (HTTP 503)."""
    status_code = 503
