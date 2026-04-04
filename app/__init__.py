import os
import signal

import logging
from dotenv import load_dotenv
from flask import Flask, jsonify

from app.database import db, init_db
from app.errors import register_error_handlers
from app.monitoring import setup_monitoring
from app.routes import register_routes


def create_app(testing=False):
    load_dotenv()

    app = Flask(__name__)
    
    # Set TESTING config BEFORE setup_monitoring to prevent Prometheus conflicts
    if testing:
        app.config["TESTING"] = True

    setup_monitoring(app)
    init_db(app)

    from app.models.user import User
    from app.models.url import ShortURL
    from app.models.event import Event

    try:
        db.connect(reuse_if_open=True)
        db.create_tables([User, ShortURL, Event], safe=True)
        if User.select().count() == 0:
            from app.seed import seed_all
            seed_all()
    except Exception:
        pass
    finally:
        if not db.is_closed():
            db.close()

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    @app.route("/logs", methods=["GET"])
    def get_logs():
        """Remote log inspection endpoint for operators.
        
        Query parameters:
        - limit: Number of log entries to return (default: 50, max: 200)
        - filter: Filter logs by keyword (case-insensitive)
        - level: Filter by log level (INFO, ERROR, WARNING, etc.)
        """
        from flask import request
        import json
        
        limit = int(request.args.get("limit", 50))
        limit = min(max(limit, 1), 200)  # Clamp between 1 and 200
        
        filter_keyword = request.args.get("filter", "").lower()
        level_filter = request.args.get("level", "").upper()
        
        # Get logs from buffer
        logs = list(app.log_buffer.buffer)[-limit:]
        
        # Parse and filter JSON logs
        result = []
        for log_entry in logs:
            try:
                parsed = json.loads(log_entry)
                
                # Apply filters
                if level_filter and parsed.get("levelname") != level_filter:
                    continue
                if filter_keyword:
                    log_str = json.dumps(parsed).lower()
                    if filter_keyword not in log_str:
                        continue
                
                result.append(parsed)
            except json.JSONDecodeError:
                # If not JSON, include raw
                if not filter_keyword or filter_keyword in log_entry.lower():
                    result.append({"raw": log_entry})
        
        return jsonify({
            "count": len(result),
            "logs": result
        })

    @app.route("/chaos")
    def chaos():
        from flask import request
        token = os.environ.get("CHAOS_TOKEN")
        if not token or request.headers.get("X-Chaos-Token") != token:
            return jsonify(error="Unauthorized"), 401
        os.kill(1, signal.SIGTERM)
        return "", 204

    register_routes(app)
    register_error_handlers(app)

    return app
