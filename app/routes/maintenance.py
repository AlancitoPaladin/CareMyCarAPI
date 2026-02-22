from calendar import monthrange
from datetime import date, datetime

from bson import ObjectId
from flask import Blueprint, request

from ..models import Maintenance, MaintenanceDue, Vehicle
from ..utils.db import get_db
from ..utils.decorators import token_required
from ..utils.validators import validate_maintenance_payload

maintenance_bp = Blueprint("maintenance", __name__)

SERVICE_RULES = [
    {"key": "oil_change", "label": "Cambio de aceite", "interval_km": 5000, "interval_months": 5},
    {"key": "tire_rotation", "label": "Rotación de llantas", "interval_km": 10000, "interval_months": 6},
    {"key": "brake_check", "label": "Revisión de frenos", "interval_km": 15000, "interval_months": 12},
    {"key": "general_service", "label": "Servicio general", "interval_km": 20000, "interval_months": 12},
]

SERVICE_TYPE_ALIASES = {
    "cambio de aceite": "oil_change",
    "oil change": "oil_change",
    "afinacion": "general_service",
    "afinação": "general_service",
    "servicio general": "general_service",
    "general service": "general_service",
    "rotacion de llantas": "tire_rotation",
    "alineacion y balanceo": "tire_rotation",
    "frenos": "brake_check",
    "revision de frenos": "brake_check",
}


def _normalize_service_type(value):
    raw = (value or "").strip().lower()
    return SERVICE_TYPE_ALIASES.get(raw, raw.replace(" ", "_"))


def _safe_parse_date(date_value):
    if not date_value:
        return None
    try:
        return datetime.strptime(str(date_value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _add_months(base_date, months):
    year = base_date.year + (base_date.month - 1 + months) // 12
    month = (base_date.month - 1 + months) % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def _compute_vehicle_due(current_user, vehicle):
    vehicle_id = vehicle["id"]
    history = Maintenance.find_by_vehicle(current_user["_id"], vehicle_id)
    current_mileage = int(vehicle.get("current_mileage") or 0)
    acquisition = _safe_parse_date(vehicle.get("acquisition_date"))
    created_at = _safe_parse_date((vehicle.get("created_at") or "")[:10])
    base_date_default = acquisition or created_at or date.today()

    last_by_type = {}
    for record in history:
        type_key = _normalize_service_type(record.get("service_type"))
        service_date = _safe_parse_date(record.get("service_date"))
        if not service_date:
            continue
        if type_key not in last_by_type or service_date > last_by_type[type_key]["service_date"]:
            last_by_type[type_key] = {
                "service_date": service_date,
                "mileage": int(record.get("mileage") or 0),
            }

    today = date.today()
    due_items = []
    for rule in SERVICE_RULES:
        last = last_by_type.get(rule["key"])
        base_date = last["service_date"] if last else base_date_default
        base_km = last["mileage"] if last else 0
        due_date = _add_months(base_date, rule["interval_months"])
        due_km = base_km + rule["interval_km"]
        days_left = (due_date - today).days
        km_left = due_km - current_mileage

        is_due = days_left <= 0 or km_left <= 0
        is_upcoming = (0 < days_left <= 30) or (0 < km_left <= 1000)
        status = "due" if is_due else "upcoming" if is_upcoming else "ok"

        due_items.append(
            {
                "service_key": rule["key"],
                "service_label": rule["label"],
                "due_date": due_date.isoformat(),
                "due_km": due_km,
                "days_left": days_left,
                "km_left": km_left,
                "status": status,
                "recommended": status in {"due", "upcoming"},
            }
        )

    has_due = any(item["status"] == "due" for item in due_items)
    has_upcoming = any(item["status"] == "upcoming" for item in due_items)
    payload = {
        "vehicle_label": f'{vehicle.get("make", "")} {vehicle.get("model", "")}'.strip() or "Vehículo",
        "current_mileage": current_mileage,
        "items": due_items,
        "has_due": has_due,
        "has_upcoming": has_upcoming,
    }
    MaintenanceDue.upsert_for_vehicle(current_user["_id"], vehicle_id, payload)
    return payload


@maintenance_bp.post("")
@token_required
def create_maintenance(current_user):
    payload = request.get_json(silent=True) or {}
    errors = validate_maintenance_payload(payload, partial=False)
    if errors:
        return {"errors": errors}, 400

    vehicle_id = payload.get("vehicle_id")
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    vehicle = Vehicle.find_by_id_for_user(vehicle_id, current_user["_id"])
    if not vehicle:
        return {"error": "Vehicle not found"}, 404

    item = Maintenance.create(current_user["_id"], payload)
    _compute_vehicle_due(current_user, vehicle)
    return {"maintenance": item}, 201


@maintenance_bp.get("/<vehicle_id>")
@token_required
def list_maintenance(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    vehicle = Vehicle.find_by_id_for_user(vehicle_id, current_user["_id"])
    if not vehicle:
        return {"error": "Vehicle not found"}, 404

    items = Maintenance.find_by_vehicle(current_user["_id"], vehicle_id)
    return {"items": items}, 200


@maintenance_bp.get("/insights/recommendations/<vehicle_id>")
@token_required
def recommendations(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    vehicle = Vehicle.find_by_id_for_user(vehicle_id, current_user["_id"])
    if not vehicle:
        return {"error": "Vehicle not found"}, 404

    payload = _compute_vehicle_due(current_user, vehicle)
    return {"vehicle_id": vehicle_id, "recommendations": payload["items"]}, 200


@maintenance_bp.get("/insights/upcoming")
@token_required
def list_upcoming(current_user):
    vehicles = Vehicle.find_all_by_user(current_user["_id"])
    for vehicle in vehicles:
        _compute_vehicle_due(current_user, vehicle)

    rows = MaintenanceDue.list_due_by_user(current_user["_id"])
    due_or_upcoming = [r for r in rows if r.get("has_due") or r.get("has_upcoming")]
    return {"items": due_or_upcoming}, 200


@maintenance_bp.get("/insights/upcoming/all")
@token_required
def list_upcoming_all(current_user):
    if str(current_user.get("role", "user")).lower() != "admin":
        return {"error": "Forbidden"}, 403

    db = get_db()
    rows = MaintenanceDue.list_all_due()
    due_or_upcoming = [r for r in rows if r.get("has_due") or r.get("has_upcoming")]

    user_ids = [r.get("user_id") for r in due_or_upcoming if r.get("user_id")]
    users = db["users"].find({"_id": {"$in": [ObjectId(uid) for uid in user_ids if ObjectId.is_valid(uid)]}})
    users_by_id = {str(u["_id"]): {"email": u.get("email"), "name": u.get("name")} for u in users}

    for row in due_or_upcoming:
        info = users_by_id.get(row.get("user_id"), {})
        row["user_email"] = info.get("email")
        row["user_name"] = info.get("name")

    return {"items": due_or_upcoming}, 200


@maintenance_bp.put("/<maintenance_id>")
@token_required
def update_maintenance(current_user, maintenance_id):
    if not ObjectId.is_valid(maintenance_id):
        return {"error": "Invalid maintenance id"}, 400

    payload = request.get_json(silent=True) or {}
    errors = validate_maintenance_payload(payload, partial=True)
    if errors:
        return {"errors": errors}, 400

    existing = Maintenance.find_by_id_for_user(maintenance_id, current_user["_id"])
    item = Maintenance.update_for_user(maintenance_id, current_user["_id"], payload)
    if not item:
        return {"error": "Maintenance record not found or empty payload"}, 404

    if existing:
        vehicle = Vehicle.find_by_id_for_user(existing.get("vehicle_id"), current_user["_id"])
        if vehicle:
            _compute_vehicle_due(current_user, vehicle)

    return {"maintenance": item}, 200


@maintenance_bp.delete("/<maintenance_id>")
@token_required
def delete_maintenance(current_user, maintenance_id):
    if not ObjectId.is_valid(maintenance_id):
        return {"error": "Invalid maintenance id"}, 400

    existing = Maintenance.find_by_id_for_user(maintenance_id, current_user["_id"])
    deleted = Maintenance.delete_for_user(maintenance_id, current_user["_id"])
    if not deleted:
        return {"error": "Maintenance record not found"}, 404

    if existing:
        vehicle = Vehicle.find_by_id_for_user(existing.get("vehicle_id"), current_user["_id"])
        if vehicle:
            _compute_vehicle_due(current_user, vehicle)

    return {"status": "deleted"}, 200
