"""Integration tests for URL shortener API endpoints."""

import json

from app.models.url import ShortURL
from app.models.user import User


class TestHealthEndpoint:
    """Tests for GET /health (Bronze — Reliability quest)."""

    def test_health_returns_200(self, client):
        """Health check endpoint should return 200 + status=ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestShortenEndpoint:
    """Tests for POST /shorten (Reliability Bronze+Silver)."""

    def test_shorten_valid_url(self, client):
        """POST /shorten with valid URL creates short link."""
        resp = client.post(
            "/shorten", json={"url": "https://example.com/very/long/path"}
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "short_code" in data
        assert data["original_url"] == "https://example.com/very/long/path"
        assert "short_url" in data

    def test_shorten_missing_url(self, client):
        """POST /shorten without 'url' field returns 400."""
        resp = client.post("/shorten", json={})
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_shorten_invalid_url(self, client):
        """POST /shorten with malformed URL returns 400."""
        resp = client.post("/shorten", json={"url": "not-a-url"})
        assert resp.status_code == 400

    def test_shorten_invalid_scheme(self, client):
        """POST /shorten with non-http(s) scheme returns 400."""
        resp = client.post("/shorten", json={"url": "ftp://example.com"})
        assert resp.status_code == 400

    def test_shorten_with_custom_code(self, client):
        """POST /shorten can accept custom short code."""
        resp = client.post(
            "/shorten",
            json={
                "url": "https://example.com",
                "custom_code": "mycode",
            },
        )
        assert resp.status_code == 201
        assert resp.get_json()["short_code"] == "mycode"

    def test_shorten_duplicate_custom_code(self, client):
        """POST /shorten with existing custom_code returns 409."""
        client.post(
            "/shorten",
            json={"url": "https://example.com", "custom_code": "taken"},
        )
        resp = client.post(
            "/shorten",
            json={"url": "https://other.com", "custom_code": "taken"},
        )
        assert resp.status_code == 409


class TestRedirectEndpoint:
    """Tests for GET /<short_code> (Scalability Bronze — caching)."""

    def test_redirect_valid_code(self, client):
        """GET /<code> with valid code redirects to original URL."""
        # Create short link first
        resp = client.post("/shorten", json={"url": "https://example.com"})
        code = resp.get_json()["short_code"]

        # Redirect should return 302 with Location header
        resp = client.get(f"/{code}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://example.com"

    def test_redirect_invalid_code(self, client):
        """GET /<nonexistent> returns 404."""
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

    def test_redirect_increments_counter(self, client):
        """Multiple redirects increment the click_count."""
        resp = client.post("/shorten", json={"url": "https://example.com"})
        code = resp.get_json()["short_code"]

        # Get before redirects
        url_obj = ShortURL.get(ShortURL.short_code == code)
        assert url_obj.click_count == 0

        # Redirect twice
        client.get(f"/{code}", follow_redirects=False)
        client.get(f"/{code}", follow_redirects=False)

        # Check counter updated
        url_obj = ShortURL.get(ShortURL.short_code == code)
        assert url_obj.click_count == 2

    def test_redirect_inactive_code(self, client):
        """GET /<deleted_code> returns 404 if is_active=false."""
        resp = client.post("/shorten", json={"url": "https://example.com"})
        code = resp.get_json()["short_code"]

        # Deactivate it
        client.delete(f"/api/urls/{code}")

        # Trying to redirect should fail
        resp = client.get(f"/{code}")
        assert resp.status_code == 404


class TestListUrlsEndpoint:
    """Tests for GET /urls (Scale test — pagination)."""

    def test_list_urls_returns_json_array(self, client):
        """GET /urls returns array of shortened URLs."""
        client.post("/shorten", json={"url": "https://example.com"})
        resp = client.get("/urls")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_urls_pagination(self, client):
        """GET /urls?limit=10 respects limit parameter."""
        # Create 5 URLs
        for i in range(5):
            client.post("/shorten", json={"url": f"https://example{i}.com"})

        resp = client.get("/urls?limit=2")
        data = resp.get_json()
        assert len(data) == 2


class TestDeactivateEndpoint:
    """Tests for DELETE /api/urls/<code>."""

    def test_deactivate_valid_code(self, client):
        """DELETE /api/urls/<code> marks URL as inactive."""
        resp = client.post("/shorten", json={"url": "https://example.com"})
        code = resp.get_json()["short_code"]

        resp = client.delete(f"/api/urls/{code}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "deleted"

        # Verify is_active = false in DB
        url_obj = ShortURL.get(ShortURL.short_code == code)
        assert url_obj.is_active is False

    def test_deactivate_nonexistent(self, client):
        """DELETE /api/urls/<nonexistent> returns 404."""
        resp = client.delete("/api/urls/nonexistent")
        assert resp.status_code == 404
