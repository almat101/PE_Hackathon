"""Seed hackathon-provided CSV data into the database."""

import csv
import json
import os

from app.database import db
from app.models.event import Event
from app.models.url import ShortURL
from app.models.user import User

CSV_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "csv")


def seed_all():
    """Load all hackathon seed data from csv/ directory into the database."""
    # Initialize Flask app context to setup database connection
    from app import create_app
    app = create_app()
    
    with app.app_context():
        # Explicitly connect to database
        db.connect(reuse_if_open=True)
        
        print("Starting seed...")
        with db.atomic():
            _seed_users()
            _seed_urls()
            _seed_events()
        print("✓ Seed complete.\n")
        
        # Close connection
        db.close()


def _seed_users():
    """Load users from csv/users.csv"""
    path = os.path.join(CSV_DIR, "users.csv")
    if not os.path.exists(path):
        print(f"⚠ Skipping users — {path} not found")
        return

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    batch = [
        {
            "id": int(row["id"]),
            "username": row["username"],
            "email": row["email"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    # Insert with conflict ignore (idempotent)
    User.insert_many(batch).on_conflict_ignore().execute()
    print(f"  ✓ Seeded {len(batch)} users")


def _seed_urls():
    """Load shortened URLs from csv/urls.csv"""
    path = os.path.join(CSV_DIR, "urls.csv")
    if not os.path.exists(path):
        print(f"⚠ Skipping urls — {path} not found")
        return

    # Get valid user IDs to handle orphaned references in CSV
    valid_user_ids = set(u.id for u in User.select(User.id))

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    batch = [
        {
            "id": int(row["id"]),
            # Validate user_id—if not in database, set to None (nullable)
            "user": int(row["user_id"]) if row.get("user_id") and int(row.get("user_id", 0)) in valid_user_ids else None,
            "short_code": row["short_code"],
            "original_url": row["original_url"],
            "title": row.get("title", ""),
            "is_active": row.get("is_active", "true").lower() == "true",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "click_count": 0,
        }
        for row in rows
    ]

    # Insert in chunks to avoid oversized queries
    chunk_size = 100
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i : i + chunk_size]
        ShortURL.insert_many(chunk).on_conflict_ignore().execute()

    print(f"  ✓ Seeded {len(batch)} URLs")


def _seed_events():
    """Load audit events from csv/events.csv"""
    path = os.path.join(CSV_DIR, "events.csv")
    if not os.path.exists(path):
        print(f"⚠ Skipping events — {path} not found")
        return

    # Get valid user and URL IDs to handle orphaned references in CSV
    valid_user_ids = set(u.id for u in User.select(User.id))
    valid_url_ids = set(u.id for u in ShortURL.select(ShortURL.id))

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    batch = [
        {
            "id": int(row["id"]),
            # Validate foreign keys—set to None if not in database
            "url": int(row["url_id"]) if row.get("url_id") and int(row.get("url_id", 0)) in valid_url_ids else None,
            "user": int(row["user_id"]) if row.get("user_id") and int(row.get("user_id", 0)) in valid_user_ids else None,
            "event_type": row["event_type"],
            "timestamp": row["timestamp"],
            "details": row.get("details", "{}"),
        }
        for row in rows
    ]

    # Insert in chunks
    chunk_size = 100
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i : i + chunk_size]
        Event.insert_many(chunk).on_conflict_ignore().execute()

    print(f"  ✓ Seeded {len(batch)} events")
