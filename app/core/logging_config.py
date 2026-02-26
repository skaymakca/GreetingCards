"""Centralized logging configuration.

Import `configure_logging` and call it once from any entry point,
or just import this module — the root logger is configured on import.
"""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
