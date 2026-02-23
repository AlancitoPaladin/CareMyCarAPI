import csv
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from flask import Blueprint, request

from ..models import Part
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


@parts_bp.get("/options")
@token_required
def parts_options(current_user):
    del current_user
    make = (request.args.get("make") or "").strip().lower()
    rows = _load_make_model_options()
    makes = sorted({row["make"] for row in rows})
    if make:
        rows = [row for row in rows if row["make"].strip().lower() == make]
    models = sorted({row["model"] for row in rows})
    years = list(range(datetime.utcnow().year + 1, 1979, -1))
    return {"categories": sorted(VALID_PART_CATEGORIES), "makes": makes, "years": years, "models": models}, 200


@parts_bp.post("")
@token_required
def create_part(current_user):
    payload = request.get_json(silent=True) or {}
    required = ["name", "category", "make", "year", "model", "price", "quantity"]
    errors = [f"{f} is required" for f in required if f not in payload]
    if errors:
        return {"errors": errors}, 400

    category = str(payload.get("category", "")).strip().lower()
    if category not in VALID_PART_CATEGORIES:
        return {"error": "invalid category"}, 400
    make = str(payload.get("make") or "").strip()
    if not make:
        return {"error": "make must not be empty"}, 400
    model = str(payload.get("model") or "").strip()
    valid_options = _load_make_model_options()
    if valid_options:
        valid_pair = any(
            row["make"].strip().lower() == make.lower() and row["model"].strip().lower() == model.lower()
            for row in valid_options
        )
        if not valid_pair:
            return {"error": "make/model not available in maintenance_costs dataset"}, 400

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

    item = Part.create(
        current_user["_id"],
        {
            "name": str(payload.get("name") or "").strip(),
            "category": category,
            "make": make,
            "year": year,
            "model": model,
            "compatibility": compatibility or [],
            "price": price,
            "quantity": quantity,
        },
    )
    return {"part": item}, 201


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

    items, total = Part.find_filtered(current_user["_id"], q=q, category=category, page=page, limit=limit)
    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
    }, 200


@parts_bp.get("/<part_id>")
@token_required
def get_part(current_user, part_id):
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400
    row = Part.find_by_id_for_user(part_id, current_user["_id"])
    if not row:
        return {"error": "Part not found"}, 404
    return {"part": row}, 200


@parts_bp.put("/<part_id>")
@token_required
def update_part(current_user, part_id):
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400

    payload = request.get_json(silent=True) or {}
    updates = {}
    allowed = {"name", "category", "make", "year", "model", "compatibility", "price", "quantity"}
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
    if "make" in updates:
        updates["make"] = str(updates["make"]).strip()
        if not updates["make"]:
            return {"error": "make must not be empty"}, 400
    if "model" in updates:
        updates["model"] = str(updates["model"]).strip()
        if not updates["model"]:
            return {"error": "model must not be empty"}, 400
    if "make" in updates or "model" in updates:
        current = Part.find_by_id_for_user(part_id, current_user["_id"])
        if not current:
            return {"error": "Part not found"}, 404
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

    row = Part.update_for_user(part_id, current_user["_id"], updates)
    if not row:
        return {"error": "Part not found"}, 404
    return {"part": row}, 200


@parts_bp.delete("/<part_id>")
@token_required
def delete_part(current_user, part_id):
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400
    deleted = Part.delete_for_user(part_id, current_user["_id"])
    if not deleted:
        return {"error": "Part not found"}, 404
    return {"status": "deleted"}, 200
