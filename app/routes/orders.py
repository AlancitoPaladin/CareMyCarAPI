import csv
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from flask import Blueprint, request

from ..models import Order, Part
from ..utils.decorators import token_required

orders_bp = Blueprint("orders", __name__)

VALID_ORDER_STATUS = {"pending", "confirmed", "delivered", "canceled"}


def _load_make_model_options():
    file_path = Path(__file__).resolve().parents[2] / "data" / "maintenance_costs.csv"
    if not file_path.exists():
        return []

    options = []
    with file_path.open("r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            make = str(row.get("make") or "").strip()
            model = str(row.get("model") or "").strip()
            if not make or not model:
                continue
            options.append({"make": make, "model": model})
    return options


@orders_bp.get("/options")
@token_required
def orders_options(current_user):
    make = (request.args.get("make") or "").strip().lower()
    model = (request.args.get("model") or "").strip().lower()
    year = request.args.get("year")

    options = _load_make_model_options()
    makes = sorted({row["make"] for row in options})
    filtered_options = options
    if make:
        filtered_options = [row for row in filtered_options if row["make"].strip().lower() == make]
    models = sorted({row["model"] for row in filtered_options})
    years = list(range(datetime.utcnow().year + 1, 1979, -1))

    filter_year = None
    if year:
        try:
            filter_year = int(year)
        except (TypeError, ValueError):
            return {"error": "year must be integer"}, 400

    part_rows = Part.find_for_order_options(current_user["_id"], make=make, model=model, year=filter_year)
    parts = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "category": p.get("category"),
            "make": p.get("make"),
            "model": p.get("model"),
            "year": p.get("year"),
            "price": p.get("price"),
            "available_quantity": p.get("quantity", 0),
        }
        for p in part_rows
    ]
    return {"years": years, "makes": makes, "models": models, "parts": parts}, 200


@orders_bp.post("")
@token_required
def create_order(current_user):
    payload = request.get_json(silent=True) or {}
    required = ["client_name", "vin", "make", "year", "model", "part_id", "quantity"]
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
    make = str(payload.get("make") or "").strip()
    if not make:
        return {"error": "make must not be empty"}, 400
    model = str(payload.get("model") or "").strip()
    if not model:
        return {"error": "model must not be empty"}, 400

    valid_options = _load_make_model_options()
    if valid_options:
        valid_pair = any(
            row["make"].strip().lower() == make.lower() and row["model"].strip().lower() == model.lower()
            for row in valid_options
        )
        if not valid_pair:
            return {"error": "make/model not available in maintenance_costs dataset"}, 400

    part = Part.find_raw_by_id_for_user(part_id, current_user["_id"])
    if not part:
        return {"error": "Part not found"}, 404
    if str(part.get("make") or "").strip().lower() != make.lower() or str(part.get("model") or "").strip().lower() != model.lower():
        return {"error": "selected part does not match make/model"}, 400

    updated_part = Part.reserve_stock(part_id, current_user["_id"], quantity)
    if not updated_part:
        return {"error": "insufficient stock"}, 400

    unit_price = float(updated_part.get("price") or 0.0)
    order = {
        "user_id": current_user["_id"],
        "client_name": str(payload.get("client_name") or "").strip(),
        "vin": str(payload.get("vin") or "").strip().upper(),
        "make": make,
        "year": year,
        "model": model,
        "part_id": part_id,
        "part_name": updated_part.get("name"),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": round(unit_price * quantity, 2),
        "status": str(payload.get("status") or "pending").strip().lower(),
    }
    if order["status"] not in VALID_ORDER_STATUS:
        order["status"] = "pending"

    created = Order.create(order)
    return {"order": created}, 201


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

    rows, total, all_count, pending_count = Order.find_filtered(
        current_user["_id"],
        q=q,
        status=status,
        page=page,
        limit=limit,
    )
    return {
        "items": rows,
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
    row = Order.find_by_id_for_user(order_id, current_user["_id"])
    if not row:
        return {"error": "Order not found"}, 404
    return {"order": row}, 200


@orders_bp.put("/<order_id>")
@token_required
def update_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    payload = request.get_json(silent=True) or {}
    allowed = {"client_name", "vin", "make", "year", "model", "status"}
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
    if "make" in updates:
        updates["make"] = str(updates["make"]).strip()
        if not updates["make"]:
            return {"error": "make must not be empty"}, 400
    if "model" in updates:
        updates["model"] = str(updates["model"]).strip()
        if not updates["model"]:
            return {"error": "model must not be empty"}, 400
    if "make" in updates or "model" in updates:
        current = Order.find_by_id_for_user(order_id, current_user["_id"])
        if not current:
            return {"error": "Order not found"}, 404
        current_make = updates.get("make", current.get("make"))
        current_model = updates.get("model", current.get("model"))
        valid_options = _load_make_model_options()
        if valid_options:
            valid_pair = any(
                row["make"].strip().lower() == str(current_make).strip().lower()
                and row["model"].strip().lower() == str(current_model).strip().lower()
                for row in valid_options
            )
            if not valid_pair:
                return {"error": "make/model not available in maintenance_costs dataset"}, 400

    row = Order.update_for_user(order_id, current_user["_id"], updates)
    if not row:
        return {"error": "Order not found"}, 404
    return {"order": row}, 200


@orders_bp.delete("/<order_id>")
@token_required
def delete_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    order = Order.find_by_id_for_user(order_id, current_user["_id"])
    if not order:
        return {"error": "Order not found"}, 404

    deleted = Order.delete_for_user(order_id, current_user["_id"])
    if not deleted:
        return {"error": "Order not found"}, 404

    part_id = order.get("part_id")
    quantity = int(order.get("quantity") or 0)
    if ObjectId.is_valid(part_id) and quantity > 0:
        Part.restore_stock(part_id, current_user["_id"], quantity)

    return {"status": "deleted"}, 200
