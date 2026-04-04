import json
import secrets
import string
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, jsonify, redirect, request
from peewee import IntegrityError
from playhouse.shortcuts import model_to_dict

from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User

urls_bp = Blueprint("urls", __name__)

CODE_ALPHABET = string.ascii_letters + string.digits


def _is_valid_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _generate_short_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def _create_unique_code() -> str:
    for _ in range(8):
        candidate = _generate_short_code()
        if not ShortURL.select().where(ShortURL.short_code == candidate).exists():
            return candidate
    raise RuntimeError("Unable to allocate short code")


@urls_bp.route("/shorten", methods=["POST"])
def shorten_url():
    payload = request.get_json(silent=True) or {}
    original_url = (payload.get("url") or payload.get("original_url") or "").strip()
    custom_code = (payload.get("custom_code") or "").strip()
    user_id = payload.get("user_id")
    title = (payload.get("title") or "").strip() or None

    if not original_url or not _is_valid_url(original_url):
        return jsonify(error="invalid url"), 400

    user = None
    if user_id is not None:
        user = User.get_or_none(User.id == user_id)
        if user is None:
            return jsonify(error="user not found"), 404

    short_code = custom_code or _create_unique_code()

    try:
        short_url = ShortURL.create(
            user=user,
            short_code=short_code,
            original_url=original_url,
            title=title,
        )
    except IntegrityError:
        return jsonify(error="short code already exists"), 409

    Event.create(
        url=short_url,
        user=user,
        event_type="created",
        details=json.dumps({"short_code": short_code}),
    )

    response_data = model_to_dict(short_url, recurse=False)
    response_data["short_url"] = f"{request.host_url}{short_code}".rstrip("/")
    return jsonify(response_data), 201


@urls_bp.route("/<string:short_code>", methods=["GET"])
def resolve_short_url(short_code: str):
    short_url = ShortURL.get_or_none(ShortURL.short_code == short_code)
    if short_url is None or not short_url.is_active:
        return jsonify(error="short code not found"), 404

    # Increment click counter
    ShortURL.update(click_count=ShortURL.click_count + 1).where(
        ShortURL.id == short_url.id
    ).execute()

    Event.create(
        url=short_url,
        user=short_url.user,
        event_type="redirected",
        details=None,
    )
    return redirect(short_url.original_url, code=302)


@urls_bp.route("/urls", methods=["GET"])
def list_urls():
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    query = ShortURL.select().order_by(ShortURL.created_at.desc()).limit(limit)
    return jsonify([model_to_dict(url, recurse=False) for url in query])


@urls_bp.route("/api/urls/<string:short_code>", methods=["DELETE"])
def deactivate_url(short_code: str):
    short_url = ShortURL.get_or_none(ShortURL.short_code == short_code)
    if short_url is None:
        return jsonify(error="short code not found"), 404

    short_url.is_active = False
    short_url.updated_at = datetime.utcnow()
    short_url.save()

    Event.create(
        url=short_url,
        user=short_url.user,
        event_type="deleted",
        details=json.dumps({"deactivated_at": datetime.utcnow().isoformat()}),
    )
    return jsonify(status="deleted", short_code=short_code), 200