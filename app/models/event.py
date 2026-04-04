from datetime import datetime

from peewee import CharField, DateTimeField, ForeignKeyField, TextField

from app.database import BaseModel
from app.models.url import ShortURL
from app.models.user import User


class Event(BaseModel):
    url = ForeignKeyField(ShortURL, backref="events", on_delete="CASCADE")
    user = ForeignKeyField(User, null=True, backref="events", on_delete="SET NULL")
    event_type = CharField(max_length=50)  # created, updated, deleted, redirected
    timestamp = DateTimeField(default=datetime.utcnow)
    details = TextField(null=True, default=None)  # JSON string

    class Meta:
        table_name = "events"