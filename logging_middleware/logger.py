import logging
import os
from typing import Optional

import requests


LOG_API_URL = os.getenv(
    "LOG_API_URL",
    "http://20.244.56.144/evaluation-service/logs",
)

VALID_STACKS = {"backend", "frontend"}
VALID_LEVELS = {"debug", "info", "warn", "error", "fatal"}
VALID_PACKAGES = {
    "cache",
    "controller",
    "cron_job",
    "db",
    "domain",
    "handler",
    "repository",
    "route",
    "service",
    "auth",
    "config",
    "middleware",
    "utils",
}


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("afford_logger")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler("app.log")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


local_logger = setup_logger()


def _auth_header(token: Optional[str] = None) -> dict:
    access_token = token or os.getenv("AFFORD_ACCESS_TOKEN")
    if not access_token:
        return {}
    return {"Authorization": f"Bearer {access_token}"}


def _clean(value: str) -> str:
    return str(value).strip().lower()


def Log(stack: str, level: str, package: str, message: str, token: Optional[str] = None) -> dict:
    stack = _clean(stack)
    level = _clean(level)
    package = _clean(package)
    message = str(message)

    if stack not in VALID_STACKS:
        raise ValueError(f"Invalid stack: {stack}")
    if level not in VALID_LEVELS:
        raise ValueError(f"Invalid level: {level}")
    if package not in VALID_PACKAGES:
        raise ValueError(f"Invalid package: {package}")

    payload = {
        "stack": stack,
        "level": level,
        "package": package,
        "message": message[:250],
    }

    local_logger.info("%s %s %s - %s", stack, level, package, message)

    try:
        response = requests.post(
            LOG_API_URL,
            json=payload,
            headers=_auth_header(token),
            timeout=3,
        )
        if response.ok:
            return response.json()
        local_logger.warning("Remote log failed: %s %s", response.status_code, response.text)
        return {"message": "local log saved", "remote_status": response.status_code}
    except requests.RequestException as exc:
        local_logger.warning("Remote log unavailable: %s", exc)
        return {"message": "local log saved", "remote_error": str(exc)}
