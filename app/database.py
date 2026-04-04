import logging
import os

from flask import jsonify
from peewee import DatabaseProxy, Model, PostgresqlDatabase

logger = logging.getLogger(__name__)

db = DatabaseProxy()


class BaseModel(Model):
    class Meta:
        database = db


def init_db(app):
    database = PostgresqlDatabase(
        os.environ.get("DATABASE_NAME", "hackathon_db"),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5432)),
        user=os.environ.get("DATABASE_USER", "postgres"),
        password=os.environ.get("DATABASE_PASSWORD", "postgres"),
    )
    db.initialize(database)

    @app.before_request
    def _db_connect():
        if not app.config.get("TESTING"):
            try:
                db.connect(reuse_if_open=True)
            except Exception:
                logger.error("Database connection failed")
                return jsonify(error="Service unavailable", status=503), 503

    @app.teardown_appcontext
    def _db_close(exc):
        if not app.config.get("TESTING") and not db.is_closed():
            db.close()
