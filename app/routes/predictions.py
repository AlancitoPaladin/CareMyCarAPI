from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, request

from ..ml_model.predict import (
    estimate_next_maintenance_cost,
    load_intervals,
    predict_next_maintenance,
)
from ..models import Maintenance, Vehicle
from ..utils.db import get_db
from ..utils.decorators import token_required

predictions_bp = Blueprint("predictions", __name__)


@predictions_bp.post("/predict/<vehicle_id>")
@token_required
def generate_prediction(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    vehicle = Vehicle.find_by_id_for_user(vehicle_id, current_user["_id"])
    if not vehicle:
        return {"error": "Vehicle not found"}, 404

    payload = request.get_json(silent=True) or {}
    service_type = payload.get("service_type", "major_service")

    history = Maintenance.find_by_vehicle(current_user["_id"], vehicle_id)
    intervals = load_intervals()

    maintenance_schedule = predict_next_maintenance(vehicle, history, intervals)
    cost_prediction = estimate_next_maintenance_cost(vehicle, history, service_type=service_type)

    prediction = {
        "maintenance_schedule": maintenance_schedule,
        "cost_prediction": cost_prediction,
    }

    db = get_db()
    db["predictions"].insert_one(
        {
            "user_id": current_user["_id"],
            "vehicle_id": vehicle_id,
            "prediction": prediction,
            "created_at": datetime.now(timezone.utc),
        }
    )

    return {"prediction": prediction}, 201


@predictions_bp.get("/predictions/<vehicle_id>")
@token_required
def get_predictions(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    db = get_db()
    records = db["predictions"].find(
        {"user_id": current_user["_id"], "vehicle_id": vehicle_id}
    ).sort("created_at", -1)

    items = []
    for rec in records:
        items.append(
            {
                "id": str(rec["_id"]),
                "vehicle_id": rec["vehicle_id"],
                "prediction": rec["prediction"],
                "created_at": rec["created_at"].isoformat() if rec.get("created_at") else None,
            }
        )

    return {"items": items}, 200
