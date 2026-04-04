import io

from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User


# ── Health ────────────────────────────────────────────────────


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ── POST /users ───────────────────────────────────────────────


def test_create_user(client):
    resp = client.post("/users", json={"username": "alice", "email": "a@t.com"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["username"] == "alice"
    assert data["email"] == "a@t.com"
    assert "id" in data
    assert "created_at" in data


def test_create_user_invalid_username(client):
    resp = client.post("/users", json={"username": 123, "email": "a@t.com"})
    assert resp.status_code == 400


def test_create_user_missing_email(client):
    resp = client.post("/users", json={"username": "bob"})
    assert resp.status_code == 400


def test_create_user_duplicate(client):
    client.post("/users", json={"username": "dup", "email": "a@t.com"})
    resp = client.post("/users", json={"username": "dup", "email": "b@t.com"})
    assert resp.status_code == 409


# ── GET /users ────────────────────────────────────────────────


def test_list_users(client):
    client.post("/users", json={"username": "u1", "email": "u1@t.com"})
    client.post("/users", json={"username": "u2", "email": "u2@t.com"})
    resp = client.get("/users")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


def test_list_users_pagination(client):
    for i in range(5):
        client.post("/users", json={"username": f"p{i}", "email": f"p{i}@t.com"})
    resp = client.get("/users?page=1&per_page=2")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


# ── GET /users/<id> ──────────────────────────────────────────


def test_get_user(client):
    r = client.post("/users", json={"username": "get1", "email": "g@t.com"})
    uid = r.get_json()["id"]
    resp = client.get(f"/users/{uid}")
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "get1"


def test_get_user_not_found(client):
    resp = client.get("/users/9999")
    assert resp.status_code == 404


# ── PUT /users/<id> ──────────────────────────────────────────


def test_update_user(client):
    r = client.post("/users", json={"username": "upd", "email": "u@t.com"})
    uid = r.get_json()["id"]
    resp = client.put(f"/users/{uid}", json={"username": "updated"})
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "updated"
    assert resp.get_json()["email"] == "u@t.com"


def test_update_user_not_found(client):
    resp = client.put("/users/9999", json={"username": "x"})
    assert resp.status_code == 404


# ── POST /users/bulk ─────────────────────────────────────────


def test_bulk_create_users(client):
    csv = b"username,email\nbulk1,b1@t.com\nbulk2,b2@t.com\n"
    data = {"file": (io.BytesIO(csv), "users.csv")}
    resp = client.post("/users/bulk", data=data, content_type="multipart/form-data")
    assert resp.status_code == 201
    assert resp.get_json()["imported"] == 2


def test_bulk_no_file(client):
    resp = client.post("/users/bulk", content_type="multipart/form-data")
    assert resp.status_code == 400


# ── POST /urls ────────────────────────────────────────────────


def test_create_url(client):
    client.post("/users", json={"username": "u", "email": "u@t.com"})
    user_id = User.select().first().id
    resp = client.post(
        "/urls",
        json={
            "user_id": user_id,
            "original_url": "https://example.com",
            "title": "Test",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["original_url"] == "https://example.com"
    assert data["user_id"] == user_id
    assert len(data["short_code"]) == 6
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data


def test_create_url_no_user(client):
    resp = client.post(
        "/urls", json={"original_url": "https://example.com", "title": "T"}
    )
    assert resp.status_code == 201
    assert resp.get_json()["user_id"] is None


def test_create_url_invalid_user(client):
    resp = client.post(
        "/urls", json={"user_id": 9999, "original_url": "https://example.com"}
    )
    assert resp.status_code == 404


def test_create_url_missing_original(client):
    resp = client.post("/urls", json={"title": "nope"})
    assert resp.status_code == 400


def test_create_url_generates_event(client):
    client.post("/urls", json={"original_url": "https://event-test.com"})
    assert Event.select().count() == 1
    ev = Event.select().first()
    assert ev.event_type == "created"


# ── GET /urls ─────────────────────────────────────────────────


def test_list_urls(client):
    client.post("/urls", json={"original_url": "https://a.com"})
    resp = client.get("/urls")
    assert resp.status_code == 200
    assert len(resp.get_json()) >= 1


def test_list_urls_filter_user(client):
    client.post("/users", json={"username": "fu", "email": "f@t.com"})
    uid = User.select().first().id
    client.post("/urls", json={"user_id": uid, "original_url": "https://a.com"})
    client.post("/urls", json={"original_url": "https://b.com"})
    resp = client.get(f"/urls?user_id={uid}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["user_id"] == uid


# ── GET /urls/<id> ────────────────────────────────────────────


def test_get_url_by_id(client):
    r = client.post("/urls", json={"original_url": "https://a.com"})
    url_id = r.get_json()["id"]
    resp = client.get(f"/urls/{url_id}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == url_id


def test_get_url_not_found(client):
    resp = client.get("/urls/9999")
    assert resp.status_code == 404


# ── PUT /urls/<id> ────────────────────────────────────────────


def test_update_url(client):
    r = client.post("/urls", json={"original_url": "https://a.com", "title": "Old"})
    url_id = r.get_json()["id"]
    resp = client.put(
        f"/urls/{url_id}", json={"title": "New Title", "is_active": False}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["title"] == "New Title"
    assert data["is_active"] is False


def test_update_url_generates_event(client):
    r = client.post("/urls", json={"original_url": "https://a.com"})
    url_id = r.get_json()["id"]
    client.put(f"/urls/{url_id}", json={"title": "X"})
    events = list(Event.select().where(Event.event_type == "updated"))
    assert len(events) == 1


def test_update_url_not_found(client):
    resp = client.put("/urls/9999", json={"title": "X"})
    assert resp.status_code == 404


# ── POST /shorten ─────────────────────────────────────────────


def test_shorten_url(client):
    resp = client.post("/shorten", json={"url": "https://example.com"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert "short_code" in data
    assert "short_url" in data
    assert data["original_url"] == "https://example.com"


def test_shorten_missing_url(client):
    resp = client.post("/shorten", json={})
    assert resp.status_code == 400


def test_shorten_invalid_url(client):
    resp = client.post("/shorten", json={"url": "ftp://bad"})
    assert resp.status_code == 400


# ── GET /<short_code> (redirect) ──────────────────────────────


def test_redirect(client):
    r = client.post("/shorten", json={"url": "https://example.com"})
    code = r.get_json()["short_code"]
    resp = client.get(f"/{code}")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://example.com"


def test_redirect_not_found(client):
    resp = client.get("/nonexistent")
    assert resp.status_code == 404


def test_redirect_increments_click(client):
    r = client.post("/shorten", json={"url": "https://click.com"})
    code = r.get_json()["short_code"]
    client.get(f"/{code}")
    client.get(f"/{code}")
    url = ShortURL.get(ShortURL.short_code == code)
    assert url.click_count == 2


# ── GET /events ───────────────────────────────────────────────


def test_list_events(client):
    client.post("/urls", json={"original_url": "https://ev.com"})
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[0]["event_type"] == "created"
    assert isinstance(data[0]["details"], dict)


def test_list_events_empty(client):
    resp = client.get("/events")
    assert resp.status_code == 200
    assert resp.get_json() == []


# ── Error handlers ────────────────────────────────────────────


def test_method_not_allowed(client):
    resp = client.delete("/shorten")
    assert resp.status_code == 405
