import logging

from django.http import JsonResponse
from django.shortcuts import render


logger = logging.getLogger("django.request")


class UserFriendlyErrorMiddleware:
    """Log unexpected errors and return a useful, non-technical response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        logger.exception("Unhandled request error on %s %s", request.method, request.path)
        message = "We couldn't complete that request. Please try again in a moment."
        accepts_json = "application/json" in request.headers.get("Accept", "")
        is_api = request.path.startswith("/api/")
        if accepts_json or is_api:
            return JsonResponse({"ok": False, "message": message}, status=500)
        return render(request, "accounts/system_error.html", {"error_message": message}, status=500)
