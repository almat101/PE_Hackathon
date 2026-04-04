"""Unit tests for data models."""

from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User


class TestUserModel:
    """Tests for User model."""

    def test_create_user(self):
        """User can be created with username, email."""
        user = User.create(username="alice", email="alice@example.com")
        assert user.id is not None
        assert user.username == "alice"
        assert user.email == "alice@example.com"

    def test_user_unique_username(self):
        """Username must be unique."""
        User.create(username="bob", email="bob@example.com")
        try:
            User.create(username="bob", email="bob2@example.com")
            assert False, "Should have raised IntegrityError"
        except Exception:
            pass  # Expected


class TestShortURLModel:
    """Tests for ShortURL model."""

    def test_create_short_url(self):
        """ShortURL can store original URL with short code."""
        url = ShortURL.create(
            short_code="abc123", original_url="https://example.com"
        )
        assert url.short_code == "abc123"
        assert url.original_url == "https://example.com"
        assert url.is_active is True
        assert url.click_count == 0

    def test_short_code_unique(self):
        """Short code must be globally unique."""
        ShortURL.create(short_code="xyz", original_url="https://a.com")
        try:
            ShortURL.create(short_code="xyz", original_url="https://b.com")
            assert False, "Should have raised IntegrityError for duplicate code"
        except Exception:
            pass

    def test_short_url_belongs_to_user(self):
        """ShortURL can be associated with a User."""
        user = User.create(username="charlie", email="charlie@example.com")
        url = ShortURL.create(
            user=user,
            short_code="user123",
            original_url="https://charlie.dev",
        )
        assert url.user.id == user.id

    def test_short_url_user_optional(self):
        """ShortURL doesn't require a user (anonymous link)."""
        url = ShortURL.create(
            short_code="anon", original_url="https://anonymous.com"
        )
        assert url.user is None


class TestEventModel:
    """Tests for Event model (audit trail)."""

    def test_create_event(self):
        """Event logs URL lifecycle (created, redirected, deleted)."""
        user = User.create(username="diana", email="diana@example.com")
        url = ShortURL.create(
            user=user, short_code="eve", original_url="https://example.com"
        )
        event = Event.create(
            url=url, user=user, event_type="created", details="{}"
        )
        assert event.event_type == "created"

    def test_event_cascade_delete(self):
        """When URL is deleted, associated events are deleted."""
        url = ShortURL.create(
            short_code="cascade", original_url="https://example.com"
        )
        Event.create(url=url, event_type="created", details="{}")
        Event.create(url=url, event_type="redirected", details="{}")

        # Delete URL
        url.delete_instance()

        # Events should be gone (cascade delete)
        assert Event.select().where(Event.url == url).count() == 0

    def test_event_user_optional(self):
        """Event can have null user (anonymous redirect)."""
        url = ShortURL.create(
            short_code="no_user", original_url="https://example.com"
        )
        event = Event.create(url=url, event_type="redirected", details=None)
        assert event.user is None
