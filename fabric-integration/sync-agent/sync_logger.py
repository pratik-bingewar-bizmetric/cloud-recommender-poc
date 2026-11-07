"""Microsoft Fabric FinOps Sync Agent - Structured Logging and Secret Redaction.

Ensures all log statements are cleanly formatted, timestamped, and sanitized
to prevent accidental leakage of bearer tokens, client secrets, or credentials.
"""

import logging
import re
from typing import Any

# Regex patterns matching OAuth bearer tokens, connection strings, or hex/base64 secrets
SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r'(access_token["\']?\s*[:=]\s*["\'])[A-Za-z0-9\-._~+/]+(["\'])', re.IGNORECASE),
    re.compile(r'(client_secret["\']?\s*[:=]\s*["\'])[^"\']+(["\'])', re.IGNORECASE),
    re.compile(r'(password["\']?\s*[:=]\s*["\'])[^"\']+(["\'])', re.IGNORECASE),
]


class TokenRedactionFilter(logging.Filter):
    """Filter that intercepts and scrubs sensitive authentication tokens and secrets."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern in SECRET_PATTERNS:
                msg = pattern.sub(
                    r"\1***REDACTED***\2" if pattern.groups == 2 else r"\1***REDACTED***", msg
                )
            record.msg = msg

        if record.args:
            cleaned_args: list[Any] = []
            for arg in record.args if isinstance(record.args, tuple) else [record.args]:
                if isinstance(arg, str):
                    s = arg
                    for pattern in SECRET_PATTERNS:
                        s = pattern.sub(r"\1***REDACTED***", s)
                    cleaned_args.append(s)
                else:
                    cleaned_args.append(arg)
            record.args = tuple(cleaned_args)

        return True


def setup_logger(name: str = "finops_sync", verbose: bool = False) -> logging.Logger:
    """Configure and return the root FinOps sync logger."""
    logger = logging.getLogger(name)
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(TokenRedactionFilter())
        logger.addHandler(handler)

    return logger
