from datetime import datetime

from peewee import BooleanField, CharField, DateTimeField, ForeignKeyField, IntegerField, TextField

from app.database import BaseModel
from app.models.user import User


class ShortURL(BaseModel):
    user = ForeignKeyField(User, null=True, backref="urls", on_delete="SET NULL")
    short_code = CharField(max_length=20, unique=True, index=True)
    original_url = TextField()
    title = CharField(max_length=255, null=True, default="")
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    click_count = IntegerField(default=0)

    class Meta:
        table_name = "urls"