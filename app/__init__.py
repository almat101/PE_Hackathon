import logging
from dotenv import load_dotenv
from flask import Flask, jsonify

from app.database import db, init_db
from app.errors import register_error_handlers
from app.monitoring import setup_monitoring
from app.routes import register_routes


def create_app():
    load_dotenv()

    app = Flask(__name__)

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

    register_routes(app)
    register_error_handlers(app)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app
