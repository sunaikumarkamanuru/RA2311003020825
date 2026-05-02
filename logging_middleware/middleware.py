from flask import request
from .logger import Log


def log_request():
    Log(
        "backend",
        "info",
        "middleware",
        f"Incoming request {request.method} {request.path}",
    )

def log_response(response):
    Log(
        "backend",
        "info",
        "middleware",
        f"Completed request {request.method} {request.path} with status {response.status_code}",
    )
    return response
