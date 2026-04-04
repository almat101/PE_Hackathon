from datetime import datetime

from peewee import CharField, DateTimeField, ForeignKeyField, TextField

from app.database import BaseModel
from app.models.url import ShortURL
from app.models.user import User


class Event(BaseModel):
    url = ForeignKeyField(ShortURL, backref="events", null=True)
    user = ForeignKeyField(User, backref="events", null=True)
    event_type = CharField(max_length=50)
    timestamp = DateTimeField(default=datetime.utcnow)
    details = TextField(default="{}")

    class Meta:
        table_name = "events"