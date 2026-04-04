from dotenv import load_dotenv
from flask import Flask, jsonify

from app.database import db, init_db
from app.errors import register_error_handlers
from app.routes import register_routes


def create_app():
    load_dotenv()

    app = Flask(__name__)

    init_db(app)

    from app import models  # noqa: F401 - registers models with Peewee
    from app.models import Event, ShortURL, User

    db.connect(reuse_if_open=True)
    db.create_tables([User, ShortURL, Event], safe=True)

    register_routes(app)
    register_error_handlers(app)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app
