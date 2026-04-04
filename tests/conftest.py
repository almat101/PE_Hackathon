import pytest
from peewee import SqliteDatabase

from app import create_app
from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User

MODELS = [User, ShortURL, Event]
test_db = SqliteDatabase(":memory:")


@pytest.fixture(autouse=True)
def setup_db():
    test_db.bind(MODELS)
    test_db.connect()
    test_db.create_tables(MODELS)
    yield
    test_db.drop_tables(MODELS)
    test_db.close()


@pytest.fixture
def app():
    application = create_app(testing=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()
