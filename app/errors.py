import logging

from flask import jsonify

logger = logging.getLogger(__name__)


def register_error_handlers(app):

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(error="Bad request", status=400), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="Not found", status=404), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify(error="Method not allowed", status=405), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.error("Internal server error: %s", e)
        return jsonify(error="Internal server error", status=500), 500

    @app.errorhandler(503)
    def service_unavailable(e):
        return jsonify(error="Service unavailable", status=503), 503

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        logger.exception("Unhandled exception: %s", e)
        return jsonify(error="Internal server error", status=500), 500
