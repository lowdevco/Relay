from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class _WriteOnlyThrottle(UserRateThrottle):
    """Only count unsafe (state-changing) requests."""

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)


class SendThrottle(_WriteOnlyThrottle):
    scope = "send"


class AIThrottle(_WriteOnlyThrottle):
    scope = "ai"
