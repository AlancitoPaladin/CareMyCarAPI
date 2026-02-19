from bson import ObjectId
from flask import Blueprint, request

from ..models import Vehicle
from ..models.vehicle_catalog import VehicleCatalog
from ..utils.decorators import token_required
from ..utils.validators import validate_vehicle_payload

vehicles_bp = Blueprint("vehicles", __name__)


def _apply_catalog_vehicle(payload):
    catalog_id = (payload.get("catalog_vehicle_id") or "").strip().lower()
    if not catalog_id:
        return payload, None

    catalog_vehicle = VehicleCatalog.find_by_id(catalog_id)
    if not catalog_vehicle:
        return payload, "catalog_vehicle_id not found in catalog"

    payload["catalog_vehicle_id"] = catalog_id
    payload["make"] = catalog_vehicle["make"]
    payload["model"] = catalog_vehicle["model"]
    payload["vehicle_type"] = catalog_vehicle["vehicle_type"]
    payload["fuel_type"] = catalog_vehicle["fuel_type"]
    payload["transmission"] = catalog_vehicle["transmission"]
    payload["image_urls"] = catalog_vehicle.get("image_urls", [])
    return payload, None


@vehicles_bp.post("")
@token_required
def create_vehicle(current_user):
    payload = request.get_json(silent=True) or {}
    payload, catalog_error = _apply_catalog_vehicle(payload)
    if catalog_error:
        return {"error": catalog_error}, 400

    errors = validate_vehicle_payload(payload, partial=False)
    if errors:
        return {"errors": errors}, 400

    item = Vehicle.create(current_user["_id"], payload)
    return {"vehicle": item}, 201


@vehicles_bp.get("")
@token_required
def list_vehicles(current_user):
    items = Vehicle.find_all_by_user(current_user["_id"])
    return {"items": items}, 200


@vehicles_bp.get("/<vehicle_id>")
@token_required
def get_vehicle(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    vehicle = Vehicle.find_by_id_for_user(vehicle_id, current_user["_id"])
    if not vehicle:
        return {"error": "Vehicle not found"}, 404

    return {"vehicle": vehicle}, 200


@vehicles_bp.put("/<vehicle_id>")
@token_required
def update_vehicle(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    payload = request.get_json(silent=True) or {}
    payload, catalog_error = _apply_catalog_vehicle(payload)
    if catalog_error:
        return {"error": catalog_error}, 400

    errors = validate_vehicle_payload(payload, partial=True)
    if errors:
        return {"errors": errors}, 400

    vehicle = Vehicle.update_for_user(vehicle_id, current_user["_id"], payload)
    if not vehicle:
        return {"error": "Vehicle not found or empty payload"}, 404

    return {"vehicle": vehicle}, 200


@vehicles_bp.delete("/<vehicle_id>")
@token_required
def delete_vehicle(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    deleted = Vehicle.delete_for_user(vehicle_id, current_user["_id"])
    if not deleted:
        return {"error": "Vehicle not found"}, 404

    return {"status": "deleted"}, 200
