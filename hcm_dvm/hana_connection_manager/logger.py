"""Centralized logging configuration for HANA Connection Manager."""

import logging
import sys
from typing import Optional


_LOG_FORMAT = "%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root():
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root = logging.getLogger("hana_conn")
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the hana_conn hierarchy."""
    _configure_root()
    return logging.getLogger(f"hana_conn.{name}")
