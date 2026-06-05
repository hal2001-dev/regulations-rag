from __future__ import annotations

import sys

from loguru import logger as _logger

_configured = False


def get_logger(name: str | None = None):
    global _configured
    if not _configured:
        _logger.remove()
        _logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan> - <level>{message}</level>",
        )
        _configured = True
    return _logger.bind(name=name) if name else _logger
