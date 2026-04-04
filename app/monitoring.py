import logging

from flask import Flask
from prometheus_flask_exporter import PrometheusMetrics
from pythonjsonlogger import jsonlogger


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

    # Add a handler to the app's logger
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # 2. Metrics
    # Exclude the /metrics endpoint itself from being tracked
    metrics = PrometheusMetrics(app, excluded_handlers=["/metrics"])
    metrics.info("app_info", "Application info", version="0.1.0")
    app.logger.info("Monitoring setup complete: JSON logging and /metrics enabled.")
