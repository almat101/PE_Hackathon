import json
from datetime import datetime

from flask import Blueprint, jsonify, redirect, request
from peewee import IntegrityError

from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User

urls_bp = Blueprint("urls", __name__)


def _fmt_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    return str(val).replace(" ", "T")


def _url_to_dict(url):
    return {
        "id": url.id,
        "user_id": url.user_id,
        "short_code": url.short_code,
        "original_url": url.original_url,
        "title": url.title,
        "is_active": bool(url.is_active),
        "created_at": _fmt_dt(url.created_at),
        "updated_at": _fmt_dt(url.updated_at),
    }


# ── POST /shorten (hackathon guide endpoint) ─────────────────


@urls_bp.route("/shorten", methods=["POST"])
def shorten():
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify(error="Missing 'url' field"), 400

    original_url = data["url"]
    if not original_url.startswith(("http://", "https://")):
        return jsonify(error="URL must start with http:// or https://"), 400

    for _ in range(10):
        code = ShortURL.generate_code()
        try:
            short = ShortURL.create(original_url=original_url, short_code=code)
            return jsonify(
                short_code=short.short_code,
                short_url=f"{request.host_url}{short.short_code}",
                original_url=short.original_url,
            ), 201
        except IntegrityError:
            continue

    return jsonify(error="Failed to generate unique code"), 500


# ── CRUD /urls (automated test endpoints) ─────────────────────


@urls_bp.route("/urls", methods=["POST"])
def create_url():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Invalid JSON"), 400

    original_url = data.get("original_url")
    if not original_url or not isinstance(original_url, str):
        return jsonify(error="Missing or invalid 'original_url'"), 400

    user_id = data.get("user_id")
    title = data.get("title", "")

    if user_id is not None:
        try:
            User.get_by_id(user_id)
        except User.DoesNotExist:
            return jsonify(error="User not found"), 404

    for _ in range(10):
        code = ShortURL.generate_code()
        try:
            url = ShortURL.create(
                user=user_id,
                original_url=original_url,
                short_code=code,
                title=title,
            )
            Event.create(
                url=url,
                user=user_id,
                event_type="created",
                details=json.dumps(
                    {"short_code": url.short_code, "original_url": url.original_url}
                ),
            )
            return jsonify(_url_to_dict(url)), 201
        except IntegrityError:
            continue

    return jsonify(error="Failed to generate unique code"), 500


@urls_bp.route("/urls", methods=["GET"])
def list_urls():
    query = ShortURL.select().order_by(ShortURL.created_at.desc())

    user_id = request.args.get("user_id", type=int)
    if user_id is not None:
        query = query.where(ShortURL.user == user_id)

    is_active = request.args.get("is_active")
    if is_active is not None:
        query = query.where(ShortURL.is_active == (is_active.lower() == "true"))

    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)
    if page and per_page:
        query = query.paginate(page, per_page)

    return jsonify([_url_to_dict(u) for u in query])


@urls_bp.route("/urls/<int:url_id>", methods=["GET"])
def get_url(url_id):
    try:
        url = ShortURL.get_by_id(url_id)
    except ShortURL.DoesNotExist:
        return jsonify(error="URL not found"), 404
    return jsonify(_url_to_dict(url))


@urls_bp.route("/urls/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    try:
        url = ShortURL.get_by_id(url_id)
    except ShortURL.DoesNotExist:
        return jsonify(error="URL not found"), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Invalid JSON"), 400

    if "title" in data:
        url.title = data["title"]
    if "is_active" in data:
        url.is_active = data["is_active"]
    if "original_url" in data:
        url.original_url = data["original_url"]

    url.updated_at = datetime.utcnow()
    url.save()

    Event.create(
        url=url,
        user=url.user_id,
        event_type="updated",
        details=json.dumps({"title": url.title, "is_active": bool(url.is_active)}),
    )

    return jsonify(_url_to_dict(url))


@urls_bp.route("/urls/<int:url_id>", methods=["DELETE"])
def delete_url(url_id):
    try:
        url = ShortURL.get_by_id(url_id)
    except ShortURL.DoesNotExist:
        return jsonify(error="URL not found"), 404

    Event.delete().where(Event.url == url_id).execute()
    url.delete_instance()
    return "", 204


# ── GET /<short_code> (redirect) ──────────────────────────────


@urls_bp.route("/<short_code>")
def redirect_url(short_code):
    try:
        short = ShortURL.get(ShortURL.short_code == short_code)
    except ShortURL.DoesNotExist:
        return jsonify(error="Short URL not found"), 404

    if not short.is_active:
        return jsonify(error="Short URL not found"), 404

    ShortURL.update(click_count=ShortURL.click_count + 1).where(
        ShortURL.id == short.id
    ).execute()

    Event.create(
        url=short,
        user=short.user_id,
        event_type="click",
        details=json.dumps(
            {"short_code": short.short_code, "original_url": short.original_url}
        ),
    )

    return redirect(short.original_url, code=302)