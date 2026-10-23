import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

from .logging import redact

logger = logging.getLogger(__name__)


class ServiceError(Exception):
    """An expected, user-reportable failure (bad configuration, provider error...)."""

    status_code = 400

    def __init__(self, message, code="service_error", status_code=None, details=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        if status_code:
            self.status_code = status_code


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ServiceError):
        return Response(
            {"detail": redact(exc.message), "code": exc.code, **({"details": exc.details} if exc.details else {})},
            status=exc.status_code,
        )
    logger.exception("Unhandled API error: %s", redact(str(exc)))
    return Response({"detail": "Internal server error.", "code": "internal_error"}, status=500)
