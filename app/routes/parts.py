from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, request
from pymongo import ReturnDocument

from ..utils.db import get_db
from ..utils.decorators import token_required

parts_bp = Blueprint("parts", __name__)

VALID_PART_CATEGORIES = {
    "frenos",
    "suspension",
    "motor",
    "transmision",
    "electrico",
    "filtros",
    "aceites",
    "llantas",
    "carroceria",
    "otros",
}


def _serialize_part(item):
    if not item:
        return None
    return {
        "id": str(item.get("_id")),
        "user_id": item.get("user_id"),
        "name": item.get("name"),
        "category": item.get("category"),
        "year": item.get("year"),
        "model": item.get("model"),
        "compatibility": item.get("compatibility", []),
        "price": item.get("price"),
        "quantity": item.get("quantity"),
        "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
        "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
    }


@parts_bp.get("/options")
@token_required
def parts_options(current_user):
    del current_user
    make = (request.args.get("make") or "").strip().lower()
    db = get_db()
    rows = list(db["vehicle_catalog"].find({}))
    if make:
        rows = [r for r in rows if str(r.get("make", "")).strip().lower() == make]
    models = sorted({str(r.get("model")).strip() for r in rows if r.get("model")})
    years = list(range(datetime.utcnow().year + 1, 1979, -1))
    return {"categories": sorted(VALID_PART_CATEGORIES), "years": years, "models": models}, 200


@parts_bp.post("")
@token_required
def create_part(current_user):
    payload = request.get_json(silent=True) or {}
    required = ["name", "category", "year", "model", "price", "quantity"]
    errors = [f"{f} is required" for f in required if f not in payload]
    if errors:
        return {"errors": errors}, 400

    category = str(payload.get("category", "")).strip().lower()
    if category not in VALID_PART_CATEGORIES:
        return {"error": "invalid category"}, 400

    try:
        year = int(payload.get("year"))
        price = float(payload.get("price"))
        quantity = int(payload.get("quantity"))
    except (TypeError, ValueError):
        return {"error": "year/price/quantity types are invalid"}, 400

    if quantity < 0 or price < 0:
        return {"error": "quantity and price must be >= 0"}, 400

    compatibility = payload.get("compatibility", [])
    if compatibility is not None and not isinstance(compatibility, list):
        return {"error": "compatibility must be a list"}, 400

    now = datetime.now(timezone.utc)
    item = {
        "user_id": current_user["_id"],
        "name": str(payload.get("name") or "").strip(),
        "category": category,
        "year": year,
        "model": str(payload.get("model") or "").strip(),
        "compatibility": compatibility or [],
        "price": price,
        "quantity": quantity,
        "created_at": now,
        "updated_at": now,
    }
    db = get_db()
    result = db["parts"].insert_one(item)
    item["_id"] = result.inserted_id
    return {"part": _serialize_part(item)}, 201


@parts_bp.get("")
@token_required
def list_parts(current_user):
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip().lower()
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(100, int(request.args.get("limit", 20))))
    except ValueError:
        return {"error": "page/limit must be integer"}, 400

    query = {"user_id": current_user["_id"]}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"model": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
            {"compatibility": {"$elemMatch": {"$regex": q, "$options": "i"}}},
        ]
    if category and category != "all":
        query["category"] = category

    db = get_db()
    collection = db["parts"]
    total = collection.count_documents(query)
    rows = collection.find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
    return {
        "items": [_serialize_part(r) for r in rows],
        "page": page,
        "limit": limit,
        "total": total,
    }, 200


@parts_bp.get("/<part_id>")
@token_required
def get_part(current_user, part_id):
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400
    db = get_db()
    row = db["parts"].find_one({"_id": ObjectId(part_id), "user_id": current_user["_id"]})
    if not row:
        return {"error": "Part not found"}, 404
    return {"part": _serialize_part(row)}, 200


@parts_bp.put("/<part_id>")
@token_required
def update_part(current_user, part_id):
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400

    payload = request.get_json(silent=True) or {}
    updates = {}
    allowed = {"name", "category", "year", "model", "compatibility", "price", "quantity"}
    for key in allowed:
        if key in payload:
            updates[key] = payload[key]
    if not updates:
        return {"error": "empty payload"}, 400

    if "category" in updates:
        updates["category"] = str(updates["category"]).strip().lower()
        if updates["category"] not in VALID_PART_CATEGORIES:
            return {"error": "invalid category"}, 400
    if "year" in updates:
        try:
            updates["year"] = int(updates["year"])
        except (TypeError, ValueError):
            return {"error": "year must be integer"}, 400
    if "price" in updates:
        try:
            updates["price"] = float(updates["price"])
        except (TypeError, ValueError):
            return {"error": "price must be numeric"}, 400
    if "quantity" in updates:
        try:
            updates["quantity"] = int(updates["quantity"])
        except (TypeError, ValueError):
            return {"error": "quantity must be integer"}, 400

    updates["updated_at"] = datetime.now(timezone.utc)
    db = get_db()
    row = db["parts"].find_one_and_update(
        {"_id": ObjectId(part_id), "user_id": current_user["_id"]},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not row:
        return {"error": "Part not found"}, 404
    return {"part": _serialize_part(row)}, 200


@parts_bp.delete("/<part_id>")
@token_required
def delete_part(current_user, part_id):
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400
    db = get_db()
    result = db["parts"].delete_one({"_id": ObjectId(part_id), "user_id": current_user["_id"]})
    if result.deleted_count == 0:
        return {"error": "Part not found"}, 404
    return {"status": "deleted"}, 200
