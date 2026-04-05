import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User

events_bp = Blueprint("events", __name__)


def _fmt_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    return str(val).replace(" ", "T")


def _event_to_dict(event):
    details = event.details
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = {}

    return {
        "id": event.id,
        "url_id": event.url_id,
        "user_id": event.user_id,
        "event_type": event.event_type,
        "timestamp": _fmt_dt(event.timestamp),
        "details": details,
    }


@events_bp.route("/events", methods=["GET"])
def list_events():
    query = Event.select().order_by(Event.timestamp.desc())

    url_id = request.args.get("url_id", type=int)
    if url_id is not None:
        query = query.where(Event.url == url_id)

    user_id = request.args.get("user_id", type=int)
    if user_id is not None:
        query = query.where(Event.user == user_id)

    event_type = request.args.get("event_type")
    if event_type is not None:
        query = query.where(Event.event_type == event_type)

    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)
    if page and per_page:
        query = query.paginate(page, per_page)

    return jsonify([_event_to_dict(e) for e in query])


@events_bp.route("/events/<int:event_id>", methods=["GET"])
def get_event(event_id):
    try:
        event = Event.get_by_id(event_id)
    except Event.DoesNotExist:
        return jsonify(error="Event not found"), 404
    return jsonify(_event_to_dict(event))


@events_bp.route("/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    try:
        event = Event.get_by_id(event_id)
    except Event.DoesNotExist:
        return jsonify(error="Event not found"), 404

    event.delete_instance()
    return "", 204


@events_bp.route("/events", methods=["POST"])
def create_event():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Invalid JSON"), 400

    event_type = data.get("event_type")
    if not event_type or not isinstance(event_type, str):
        return jsonify(error="Missing or invalid 'event_type'"), 400

    url_id = data.get("url_id")
    user_id = data.get("user_id")
    details = data.get("details", {})

    if not isinstance(details, dict):
        return jsonify(error="'details' must be a JSON object"), 400

    if url_id is not None:
        try:
            ShortURL.get_by_id(url_id)
        except ShortURL.DoesNotExist:
            return jsonify(error="URL not found"), 404

    if user_id is not None:
        try:
            User.get_by_id(user_id)
        except User.DoesNotExist:
            return jsonify(error="User not found"), 404

    event = Event.create(
        url=url_id,
        user=user_id,
        event_type=event_type,
        details=json.dumps(details) if isinstance(details, dict) else details,
    )

    return jsonify(_event_to_dict(event)), 201
