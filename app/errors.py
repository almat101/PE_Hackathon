from flask import jsonify


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
        return jsonify(error="Internal server error", status=500), 500
