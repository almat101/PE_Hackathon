import random
import string
from datetime import datetime

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    TextField,
)

from app.database import BaseModel
from app.models.user import User


class ShortURL(BaseModel):
    user = ForeignKeyField(User, backref="urls", null=True)
    original_url = TextField()
    short_code = CharField(max_length=10, unique=True, index=True)
    title = CharField(max_length=255, default="")
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    click_count = IntegerField(default=0)

    class Meta:
        table_name = "short_urls"

    @staticmethod
    def generate_code(length=6):
        chars = string.ascii_letters + string.digits
        return "".join(random.choices(chars, k=length))