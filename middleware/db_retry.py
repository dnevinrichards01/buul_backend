import psycopg2
from psycopg2 import OperationalError
from accumate_backend.retry_db import retry_on_db_error

class DBRetryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        @retry_on_db_error
        def get_response_custom(request):
            return self.get_response(request)
        self._get_response_custom = get_response_custom


    def __call__(self, request):
        return self._get_response_custom(request)