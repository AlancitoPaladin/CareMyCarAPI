import json
from pathlib import Path

from flask import Blueprint, request

from ..models.vehicle_catalog import VehicleCatalog

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.post("/vehicles/seed")
def seed_catalog_vehicles():
    payload = request.get_json(silent=True)

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
    else:
        file_path = Path(__file__).resolve().parents[2] / "data" / "vehicle_catalog.json"
        if not file_path.exists():
            return {"error": "No input payload and default catalog file not found"}, 400
        with file_path.open("r", encoding="utf-8") as f:
            items = json.load(f)

    upserted = VehicleCatalog.upsert_many(items)
    return {"status": "ok", "total_items": len(items), "inserted_new": upserted}, 200


@catalog_bp.get("/vehicles")
def list_catalog_vehicles():
    items = VehicleCatalog.find_all()
    return {"items": items}, 200


@catalog_bp.get("/vehicles/<catalog_id>")
def get_catalog_vehicle(catalog_id):
    item = VehicleCatalog.find_by_id(catalog_id)
    if not item:
        return {"error": "Catalog vehicle not found"}, 404
    return {"item": item}, 200
