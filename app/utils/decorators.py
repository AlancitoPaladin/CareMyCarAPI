from functools import wraps

from flask import request

from ..models import User
from ..routes.shared import decode_token



def token_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        parts = auth_header.split()

        if len(parts) != 2 or parts[0].lower() != "bearer":
            return {"error": "Missing or invalid token"}, 401

        user_id = decode_token(parts[1])
        if not user_id:
            return {"error": "Invalid token"}, 401

        user = User.find_by_id(user_id)
        if not user:
            return {"error": "User not found"}, 404

        return func(user, *args, **kwargs)

    return wrapper
