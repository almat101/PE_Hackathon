"""Pytest fixtures for testing — in-memory SQLite database."""

import pytest
from peewee import SqliteDatabase

from app import create_app
from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User

# Use in-memory SQLite for tests — fast and isolated
TEST_DB = SqliteDatabase(":memory:")


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    models = [User, ShortURL, Event]
    TEST_DB.bind(models)
    TEST_DB.connect(reuse_if_open=True)
    TEST_DB.create_tables(models)
    yield
    TEST_DB.drop_tables(models)
    TEST_DB.close()


@pytest.fixture
def app():
    """Create Flask test app."""
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()
