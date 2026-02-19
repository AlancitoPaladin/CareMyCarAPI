from flask import Blueprint, request

from ..models import User
from ..utils.decorators import token_required
from ..utils.validators import validate_email, validate_password
from .shared import create_access_token

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    name = (payload.get("name") or "").strip() or None

    if not validate_email(email):
        return {"error": "Invalid email"}, 400
    if not validate_password(password):
        return {"error": "Invalid password"}, 400

    if User.find_by_email(email):
        return {"error": "Email already registered"}, 409

    created = User.create(email=email, password=password, name=name)
    return {"user": User.to_public(created)}, 201


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    user = User.find_by_email(email)
    if not user or not User.verify_password(user, password):
        return {"error": "Invalid credentials"}, 401

    token = create_access_token(user["_id"])
    return {"access_token": token, "user": User.to_public(user)}, 200


@auth_bp.get("/profile")
@token_required
def profile(current_user):
    return {"user": User.to_public(current_user)}, 200
