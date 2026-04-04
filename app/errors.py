"""Global error handlers for Flask app."""

from flask import jsonify


def register_error_handlers(app):
    """Register all Flask error handlers."""

    @app.errorhandler(400)
    def bad_request(e):
        """400: Bad Request — malformed payload or validation error."""
        return jsonify(error="bad request", status=400), 400

    @app.errorhandler(404)
    def not_found(e):
        """404: Not Found — resource doesn't exist."""
        return jsonify(error="not found", status=404), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        """405: Method Not Allowed — wrong HTTP verb."""
        return jsonify(error="method not allowed", status=405), 405

    @app.errorhandler(409)
    def conflict(e):
        """409: Conflict — duplicate resource (e.g., short code exists)."""
        return jsonify(error="conflict", status=409), 409

    @app.errorhandler(500)
    def internal_error(e):
        """500: Internal Server Error."""
        # In production, log the full error somewhere
        return jsonify(error="internal server error", status=500), 500

    @app.errorhandler(503)
    def service_unavailable(e):
        """503: Service Unavailable — DB or Redis down."""
        return jsonify(error="service unavailable", status=503), 503
