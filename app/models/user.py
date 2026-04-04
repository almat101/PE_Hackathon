from datetime import datetime

from peewee import CharField, DateTimeField

from app.database import BaseModel


class User(BaseModel):
    username = CharField(max_length=100, unique=True)
    email = CharField(max_length=255)
    created_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        table_name = "users"