import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.models.event import Event

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

    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)
    if page and per_page:
        query = query.paginate(page, per_page)

    return jsonify([_event_to_dict(e) for e in query])
