"""Centralized logging configuration.

Import this module from any entry point — the root logger is configured
at import time via ``logging.basicConfig``.
"""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S")
