from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from werkzeug.security import check_password_hash, generate_password_hash

from ..utils.db import get_db


class User:
    collection = "users"

    @staticmethod
    def create(email, password, name=None):
        db = get_db()
        now = datetime.now(timezone.utc)
        user = {
            "email": email,
            "password_hash": generate_password_hash(password),
            "name": name,
            "created_at": now,
        }
        inserted = db[User.collection].insert_one(user)
        user["_id"] = inserted.inserted_id
        return User.serialize(user)

    @staticmethod
    def find_by_email(email):
        db = get_db()
        user = db[User.collection].find_one({"email": email})
        return User.serialize(user) if user else None

    @staticmethod
    def find_by_id(user_id):
        db = get_db()
        try:
            user = db[User.collection].find_one({"_id": ObjectId(user_id)})
        except InvalidId:
            return None
        return User.serialize(user) if user else None

    @staticmethod
    def verify_password(user, password):
        return check_password_hash(user["password_hash"], password)

    @staticmethod
    def to_public(user):
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user.get("name"),
            "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
        }

    @staticmethod
    def serialize(user):
        if not user:
            return None
        user["_id"] = str(user["_id"])
        return user
