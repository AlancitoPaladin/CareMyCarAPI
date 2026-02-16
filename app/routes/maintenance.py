from bson import ObjectId
from flask import Blueprint, request

from ..models import Maintenance, Vehicle
from ..utils.decorators import token_required
from ..utils.validators import validate_maintenance_payload

maintenance_bp = Blueprint("maintenance", __name__)


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


@maintenance_bp.put("/<maintenance_id>")
@token_required
def update_maintenance(current_user, maintenance_id):
    if not ObjectId.is_valid(maintenance_id):
        return {"error": "Invalid maintenance id"}, 400

    payload = request.get_json(silent=True) or {}
    errors = validate_maintenance_payload(payload, partial=True)
    if errors:
        return {"errors": errors}, 400

    item = Maintenance.update_for_user(maintenance_id, current_user["_id"], payload)
    if not item:
        return {"error": "Maintenance record not found or empty payload"}, 404

    return {"maintenance": item}, 200


@maintenance_bp.delete("/<maintenance_id>")
@token_required
def delete_maintenance(current_user, maintenance_id):
    if not ObjectId.is_valid(maintenance_id):
        return {"error": "Invalid maintenance id"}, 400

    deleted = Maintenance.delete_for_user(maintenance_id, current_user["_id"])
    if not deleted:
        return {"error": "Maintenance record not found"}, 404

    return {"status": "deleted"}, 200
