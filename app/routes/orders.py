from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, request
from pymongo import ReturnDocument

from ..utils.db import get_db
from ..utils.decorators import token_required

orders_bp = Blueprint("orders", __name__)

VALID_ORDER_STATUS = {"pending", "confirmed", "delivered", "canceled"}


def _serialize_order(item):
    if not item:
        return None
    return {
        "id": str(item.get("_id")),
        "user_id": item.get("user_id"),
        "client_name": item.get("client_name"),
        "vin": item.get("vin"),
        "year": item.get("year"),
        "model": item.get("model"),
        "part_id": item.get("part_id"),
        "part_name": item.get("part_name"),
        "quantity": item.get("quantity"),
        "unit_price": item.get("unit_price"),
        "total_price": item.get("total_price"),
        "status": item.get("status"),
        "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
        "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
    }


@orders_bp.get("/options")
@token_required
def orders_options(current_user):
    model = (request.args.get("model") or "").strip().lower()
    year = request.args.get("year")

    db = get_db()
    catalog_rows = list(db["vehicle_catalog"].find({}))
    models = sorted({str(r.get("model")).strip() for r in catalog_rows if r.get("model")})
    years = list(range(datetime.utcnow().year + 1, 1979, -1))

    parts_query = {"user_id": current_user["_id"]}
    if model:
        parts_query["$or"] = [
            {"model": {"$regex": f"^{model}$", "$options": "i"}},
            {"compatibility": {"$elemMatch": {"$regex": f"^{model}$", "$options": "i"}}},
        ]
    if year:
        try:
            parts_query["year"] = int(year)
        except (TypeError, ValueError):
            return {"error": "year must be integer"}, 400

    part_rows = db["parts"].find(parts_query).sort("created_at", -1)
    parts = [
        {
            "id": str(p.get("_id")),
            "name": p.get("name"),
            "category": p.get("category"),
            "model": p.get("model"),
            "year": p.get("year"),
            "price": p.get("price"),
            "available_quantity": p.get("quantity", 0),
        }
        for p in part_rows
    ]
    return {"years": years, "models": models, "parts": parts}, 200


@orders_bp.post("")
@token_required
def create_order(current_user):
    payload = request.get_json(silent=True) or {}
    required = ["client_name", "vin", "year", "model", "part_id", "quantity"]
    errors = [f"{f} is required" for f in required if f not in payload]
    if errors:
        return {"errors": errors}, 400

    part_id = payload.get("part_id")
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400

    try:
        quantity = int(payload.get("quantity"))
        year = int(payload.get("year"))
    except (TypeError, ValueError):
        return {"error": "quantity/year types are invalid"}, 400
    if quantity <= 0:
        return {"error": "quantity must be > 0"}, 400

    db = get_db()
    part = db["parts"].find_one({"_id": ObjectId(part_id), "user_id": current_user["_id"]})
    if not part:
        return {"error": "Part not found"}, 404
    available = int(part.get("quantity") or 0)
    if available < quantity:
        return {"error": "insufficient stock"}, 400

    db["parts"].update_one(
        {"_id": ObjectId(part_id), "user_id": current_user["_id"]},
        {"$inc": {"quantity": -quantity}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )

    unit_price = float(part.get("price") or 0.0)
    now = datetime.now(timezone.utc)
    order = {
        "user_id": current_user["_id"],
        "client_name": str(payload.get("client_name") or "").strip(),
        "vin": str(payload.get("vin") or "").strip().upper(),
        "year": year,
        "model": str(payload.get("model") or "").strip(),
        "part_id": part_id,
        "part_name": part.get("name"),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": round(unit_price * quantity, 2),
        "status": str(payload.get("status") or "pending").strip().lower(),
        "created_at": now,
        "updated_at": now,
    }
    if order["status"] not in VALID_ORDER_STATUS:
        order["status"] = "pending"

    result = db["orders"].insert_one(order)
    order["_id"] = result.inserted_id
    return {"order": _serialize_order(order)}, 201


@orders_bp.get("")
@token_required
def list_orders(current_user):
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip().lower()
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(100, int(request.args.get("limit", 20))))
    except ValueError:
        return {"error": "page/limit must be integer"}, 400

    if status and status != "all" and status not in VALID_ORDER_STATUS:
        return {"error": "invalid status"}, 400

    query_base = {"user_id": current_user["_id"]}
    if q:
        query_base["$or"] = [
            {"client_name": {"$regex": q, "$options": "i"}},
            {"part_name": {"$regex": q, "$options": "i"}},
            {"vin": {"$regex": q, "$options": "i"}},
            {"model": {"$regex": q, "$options": "i"}},
        ]

    query = dict(query_base)
    if status and status != "all":
        query["status"] = status

    db = get_db()
    collection = db["orders"]
    total = collection.count_documents(query)
    all_count = collection.count_documents(query_base)
    pending_count = collection.count_documents({**query_base, "status": "pending"})

    rows = collection.find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
    return {
        "items": [_serialize_order(r) for r in rows],
        "page": page,
        "limit": limit,
        "total": total,
        "all_count": all_count,
        "pending_count": pending_count,
    }, 200


@orders_bp.get("/<order_id>")
@token_required
def get_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    db = get_db()
    row = db["orders"].find_one({"_id": ObjectId(order_id), "user_id": current_user["_id"]})
    if not row:
        return {"error": "Order not found"}, 404
    return {"order": _serialize_order(row)}, 200


@orders_bp.put("/<order_id>")
@token_required
def update_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    payload = request.get_json(silent=True) or {}
    allowed = {"client_name", "vin", "year", "model", "status"}
    updates = {k: payload[k] for k in allowed if k in payload}
    if not updates:
        return {"error": "empty payload"}, 400

    if "status" in updates:
        updates["status"] = str(updates["status"]).strip().lower()
        if updates["status"] not in VALID_ORDER_STATUS:
            return {"error": "invalid status"}, 400
    if "year" in updates:
        try:
            updates["year"] = int(updates["year"])
        except (TypeError, ValueError):
            return {"error": "year must be integer"}, 400
    if "vin" in updates:
        updates["vin"] = str(updates["vin"]).strip().upper()

    updates["updated_at"] = datetime.now(timezone.utc)
    db = get_db()
    row = db["orders"].find_one_and_update(
        {"_id": ObjectId(order_id), "user_id": current_user["_id"]},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not row:
        return {"error": "Order not found"}, 404
    return {"order": _serialize_order(row)}, 200


@orders_bp.delete("/<order_id>")
@token_required
def delete_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    db = get_db()
    order = db["orders"].find_one({"_id": ObjectId(order_id), "user_id": current_user["_id"]})
    if not order:
        return {"error": "Order not found"}, 404

    db["orders"].delete_one({"_id": ObjectId(order_id), "user_id": current_user["_id"]})

    part_id = order.get("part_id")
    quantity = int(order.get("quantity") or 0)
    if ObjectId.is_valid(part_id) and quantity > 0:
        db["parts"].update_one(
            {"_id": ObjectId(part_id), "user_id": current_user["_id"]},
            {"$inc": {"quantity": quantity}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    return {"status": "deleted"}, 200
