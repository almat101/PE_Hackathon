import logging
import os
from pathlib import Path

from flask import Flask
from prometheus_flask_exporter import PrometheusMetrics
from pythonjsonlogger import jsonlogger


# Store log entries in memory (max 1000 entries)
class LogBuffer(logging.Handler):
    def __init__(self, maxlen=1000):
        super().__init__()
        self.buffer = collections.deque(maxlen=maxlen)
    
    def emit(self, record):
        try:
            msg = self.format(record)
            self.buffer.append(msg)
        except Exception:
            self.handleError(record)


# Import at module level
import collections


def setup_monitoring(app: Flask):
    """Configure logging and metrics for the Flask app."""

    # 1. Structured Logging
    # Disable default handlers to avoid duplicate logs
    for handler in app.logger.handlers:
        app.logger.removeHandler(handler)
    for handler in logging.getLogger("werkzeug").handlers:
        logging.getLogger("werkzeug").removeHandler(handler)

    # Create a JSON formatter
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s "
        "%(pathname)s %(lineno)d"
    )

    # Add handlers to the app's logger
    # 1a. Stream handler (for docker logs)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    # 1b. Buffer handler (for API access)
    log_buffer = LogBuffer(maxlen=1000)
    log_buffer.setFormatter(formatter)
    
    app.logger.addHandler(stream_handler)
    app.logger.addHandler(log_buffer)
    app.logger.setLevel(logging.INFO)
    
    # Store log buffer on app for access via API
    app.log_buffer = log_buffer

    # 2. Metrics (skip during testing to avoid registry conflicts)
    if not app.config.get("TESTING"):
        # Exclude the /metrics endpoint itself from being tracked
        metrics = PrometheusMetrics(app, excluded_handlers=["/metrics"])
        metrics.info("app_info", "Application info", version="0.1.0")
        app.logger.info("Monitoring setup complete: JSON logging and /metrics enabled.")
    else:
        app.logger.info("Monitoring setup: JSON logging enabled (metrics disabled in TESTING mode).")
