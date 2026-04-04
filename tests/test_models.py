import pytest
from peewee import IntegrityError

from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User


# ── ShortURL.generate_code() ──────────────────────────────────


def test_generate_code_default_length():
    code = ShortURL.generate_code()
    assert len(code) == 6


def test_generate_code_custom_length():
    for length in (1, 4, 8, 12):
        assert len(ShortURL.generate_code(length=length)) == length


def test_generate_code_alphanumeric():
    code = ShortURL.generate_code(length=50)
    assert code.isalnum()


def test_generate_code_returns_string():
    assert isinstance(ShortURL.generate_code(), str)


def test_generate_code_not_constant():
    codes = {ShortURL.generate_code() for _ in range(20)}
    assert len(codes) > 1


# ── User model ────────────────────────────────────────────────


def test_create_user():
    user = User.create(username="alice", email="alice@test.com")
    assert user.id is not None
    assert user.username == "alice"
    assert user.email == "alice@test.com"
    assert user.created_at is not None


def test_user_unique_username():
    User.create(username="bob", email="one@test.com")
    with pytest.raises(IntegrityError):
        User.create(username="bob", email="two@test.com")


def test_user_table_name():
    assert User._meta.table_name == "users"


# ── ShortURL model ────────────────────────────────────────────


def test_create_short_url():
    url = ShortURL.create(original_url="https://example.com", short_code="abc123")
    assert url.id is not None
    assert url.original_url == "https://example.com"
    assert url.short_code == "abc123"


def test_short_url_defaults():
    url = ShortURL.create(original_url="https://example.com", short_code="def456")
    assert url.click_count == 0
    assert url.is_active is True
    assert url.title == ""
    assert url.created_at is not None
    assert url.updated_at is not None
    assert url.user is None


def test_short_code_unique():
    ShortURL.create(original_url="https://a.com", short_code="dup1")
    with pytest.raises(IntegrityError):
        ShortURL.create(original_url="https://b.com", short_code="dup1")


def test_short_url_with_user():
    user = User.create(username="charlie", email="c@test.com")
    url = ShortURL.create(user=user, short_code="u1", original_url="https://x.com")
    assert url.user.id == user.id


def test_short_url_user_optional():
    url = ShortURL.create(short_code="anon", original_url="https://anon.com")
    assert url.user is None


def test_short_url_click_count_increment():
    url = ShortURL.create(original_url="https://x.com", short_code="clk1")
    assert url.click_count == 0
    ShortURL.update(click_count=ShortURL.click_count + 1).where(
        ShortURL.id == url.id
    ).execute()
    url = ShortURL.get_by_id(url.id)
    assert url.click_count == 1


def test_short_url_table_name():
    assert ShortURL._meta.table_name == "short_urls"


# ── Event model ───────────────────────────────────────────────


def test_create_event():
    url = ShortURL.create(original_url="https://example.com", short_code="ev1")
    event = Event.create(url=url, event_type="created", details='{"key":"val"}')
    assert event.id is not None
    assert event.event_type == "created"
    assert event.details == '{"key":"val"}'
    assert event.timestamp is not None


def test_event_defaults():
    url = ShortURL.create(original_url="https://x.com", short_code="ev2")
    event = Event.create(url=url, event_type="redirected")
    assert event.details == "{}"
    assert event.user is None
    assert event.timestamp is not None


def test_event_with_user():
    user = User.create(username="eve", email="eve@test.com")
    url = ShortURL.create(original_url="https://x.com", short_code="ev3")
    event = Event.create(url=url, user=user, event_type="created")
    assert event.user.id == user.id


def test_event_url_optional():
    event = Event.create(event_type="system_check")
    assert event.url is None


def test_event_table_name():
    assert Event._meta.table_name == "events"
