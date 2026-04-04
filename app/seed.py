import csv
import os

from app.database import db
from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User

CSV_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "csv")


def seed_all():
    """Load hackathon seed data from csv/ directory into the database."""
    with db.atomic():
        _seed_users()
        _seed_urls()
        _seed_events()
    _reset_sequences()
    print("Seed complete.")


def _reset_sequences():
    """Reset PostgreSQL sequences after seeding with explicit IDs."""
    for table, model in [("users", User), ("short_urls", ShortURL), ("events", Event)]:
        try:
            db.execute_sql(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
        except Exception:
            pass


def _seed_users():
    path = os.path.join(CSV_DIR, "users.csv")
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        batch = [
            {
                "id": int(row["id"]),
                "username": row["username"],
                "email": row["email"],
                "created_at": row["created_at"],
            }
            for row in reader
        ]
    User.insert_many(batch).on_conflict_ignore().execute()
    print(f"  Seeded {len(batch)} users")


def _seed_urls():
    path = os.path.join(CSV_DIR, "urls.csv")
    valid_user_ids = set(u.id for u in User.select(User.id))
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        batch = [
            {
                "id": int(row["id"]),
                "user": int(row["user_id"]) if int(row["user_id"]) in valid_user_ids else None,
                "short_code": row["short_code"],
                "original_url": row["original_url"],
                "title": row["title"],
                "is_active": row["is_active"] == "True",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in reader
        ]
    for i in range(0, len(batch), 100):
        ShortURL.insert_many(batch[i : i + 100]).on_conflict_ignore().execute()
    print(f"  Seeded {len(batch)} URLs")


def _seed_events():
    path = os.path.join(CSV_DIR, "events.csv")
    valid_user_ids = set(u.id for u in User.select(User.id))
    valid_url_ids = set(u.id for u in ShortURL.select(ShortURL.id))
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        batch = [
            {
                "id": int(row["id"]),
                "url": int(row["url_id"]) if int(row["url_id"]) in valid_url_ids else None,
                "user": int(row["user_id"]) if int(row["user_id"]) in valid_user_ids else None,
                "event_type": row["event_type"],
                "timestamp": row["timestamp"],
                "details": row["details"],
            }
            for row in reader
        ]
    for i in range(0, len(batch), 100):
        Event.insert_many(batch[i : i + 100]).on_conflict_ignore().execute()
    print(f"  Seeded {len(batch)} events")
