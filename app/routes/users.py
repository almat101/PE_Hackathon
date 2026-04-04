import csv
import io
from datetime import datetime

from flask import Blueprint, jsonify, request
from peewee import IntegrityError

from app.models.user import User

users_bp = Blueprint("users", __name__)


def _fmt_dt(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    return str(val).replace(" ", "T")


def _user_to_dict(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": _fmt_dt(user.created_at),
    }


@users_bp.route("/users", methods=["GET"])
def list_users():
    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)

    query = User.select().order_by(User.id)

    if page and per_page:
        query = query.paginate(page, per_page)

    return jsonify([_user_to_dict(u) for u in query])


@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify(error="User not found"), 404
    return jsonify(_user_to_dict(user))


@users_bp.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Invalid JSON"), 400

    username = data.get("username")
    email = data.get("email")

    if not isinstance(username, str) or not username.strip():
        return jsonify(error="Invalid or missing username"), 400
    if not isinstance(email, str) or not email.strip():
        return jsonify(error="Invalid or missing email"), 400

    try:
        user = User.create(username=username.strip(), email=email.strip())
    except IntegrityError:
        return jsonify(error="Username already exists"), 409

    return jsonify(_user_to_dict(user)), 201


@users_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify(error="User not found"), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Invalid JSON"), 400

    if "username" in data:
        if not isinstance(data["username"], str) or not data["username"].strip():
            return jsonify(error="Invalid username"), 400
        user.username = data["username"].strip()
    if "email" in data:
        if not isinstance(data["email"], str) or not data["email"].strip():
            return jsonify(error="Invalid email"), 400
        user.email = data["email"].strip()

    try:
        user.save()
    except IntegrityError:
        return jsonify(error="Username already exists"), 409

    return jsonify(_user_to_dict(user))


@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    try:
        user = User.get_by_id(user_id)
    except User.DoesNotExist:
        return jsonify(error="User not found"), 404

    user.delete_instance()
    return "", 204

@users_bp.route("/users/bulk", methods=["POST"])
def bulk_create_users():
    if "file" not in request.files:
        return jsonify(error="No file provided"), 400

    file = request.files["file"]
    content = file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))

    rows = list(reader)
    if not rows:
        return jsonify(imported=0), 201

    batch = []
    for row in rows:
        try:
            entry = {"username": row["username"], "email": row["email"]}
            if "created_at" in row and row["created_at"]:
                entry["created_at"] = row["created_at"]
            batch.append(entry)
        except KeyError:
            continue

    if batch:
        for i in range(0, len(batch), 100):
            User.insert_many(batch[i : i + 100]).on_conflict(
                conflict_target=[User.username],
                preserve=[User.email],
            ).execute()

    return jsonify(imported=len(batch)), 201
