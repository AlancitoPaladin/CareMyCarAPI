from bson import ObjectId
from flask import Blueprint, request

from ..models import Vehicle
from ..utils.decorators import token_required
from ..utils.validators import validate_vehicle_payload

vehicles_bp = Blueprint("vehicles", __name__)


@vehicles_bp.post("")
@token_required
def create_vehicle(current_user):
    payload = request.get_json(silent=True) or {}
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
