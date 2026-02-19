from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from ..utils.db import get_db


class Vehicle:
    collection = "vehicles"
    updatable_fields = [
        "catalog_vehicle_id",
        "make",
        "model",
        "year",
        "vehicle_type",
        "fuel_type",
        "cylinders",
        "transmission",
        "vin",
        "license_plate",
        "color",
        "current_mileage",
        "average_mileage_daily",
        "average_mileage_weekly",
        "average_mileage_monthly",
        "engine_hours",
        "acquisition_date",
        "usage_type",
        "driving_conditions",
        "image_urls",
        "maintenance_history",
    ]

    @staticmethod
    def create(user_id, payload):
        db = get_db()
        now = datetime.now(timezone.utc)
        vehicle = {
            "user_id": user_id,
            "catalog_vehicle_id": payload.get("catalog_vehicle_id"),
            "make": payload.get("make"),
            "model": payload.get("model"),
            "year": payload.get("year"),
            "vehicle_type": payload.get("vehicle_type"),
            "fuel_type": payload.get("fuel_type"),
            "cylinders": payload.get("cylinders"),
            "transmission": payload.get("transmission"),
            "vin": payload.get("vin"),
            "license_plate": payload.get("license_plate"),
            "color": payload.get("color"),
            "current_mileage": payload.get("current_mileage", payload.get("mileage", 0)),
            "average_mileage_daily": payload.get("average_mileage_daily"),
            "average_mileage_weekly": payload.get("average_mileage_weekly"),
            "average_mileage_monthly": payload.get("average_mileage_monthly"),
            "engine_hours": payload.get("engine_hours"),
            "acquisition_date": payload.get("acquisition_date"),
            "usage_type": payload.get("usage_type"),
            "driving_conditions": payload.get("driving_conditions"),
            "image_urls": payload.get("image_urls", []),
            "maintenance_history": payload.get("maintenance_history", {}),
            "created_at": now,
            "updated_at": now,
        }
        inserted = db[Vehicle.collection].insert_one(vehicle)
        vehicle["_id"] = inserted.inserted_id
        return Vehicle.serialize(vehicle)

    @staticmethod
    def find_all_by_user(user_id):
        db = get_db()
        items = db[Vehicle.collection].find({"user_id": user_id}).sort("created_at", -1)
        return [Vehicle.serialize(v) for v in items]

    @staticmethod
    def find_by_id_for_user(vehicle_id, user_id):
        db = get_db()
        item = db[Vehicle.collection].find_one({"_id": ObjectId(vehicle_id), "user_id": user_id})
        return Vehicle.serialize(item) if item else None

    @staticmethod
    def update_for_user(vehicle_id, user_id, payload):
        db = get_db()
        updates = {
            key: payload[key]
            for key in Vehicle.updatable_fields
            if key in payload
        }
        if "mileage" in payload and "current_mileage" not in payload:
            updates["current_mileage"] = payload["mileage"]
        if not updates:
            return None

        updates["updated_at"] = datetime.now(timezone.utc)
        result = db[Vehicle.collection].find_one_and_update(
            {"_id": ObjectId(vehicle_id), "user_id": user_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return Vehicle.serialize(result) if result else None

    @staticmethod
    def delete_for_user(vehicle_id, user_id):
        db = get_db()
        result = db[Vehicle.collection].delete_one({"_id": ObjectId(vehicle_id), "user_id": user_id})
        return result.deleted_count > 0

    @staticmethod
    def serialize(vehicle):
        if not vehicle:
            return None
        vehicle["id"] = str(vehicle.pop("_id"))
        return {
            "id": vehicle["id"],
            "user_id": vehicle["user_id"],
            "catalog_vehicle_id": vehicle.get("catalog_vehicle_id"),
            "make": vehicle.get("make"),
            "model": vehicle.get("model"),
            "year": vehicle.get("year"),
            "vehicle_type": vehicle.get("vehicle_type"),
            "fuel_type": vehicle.get("fuel_type"),
            "cylinders": vehicle.get("cylinders"),
            "transmission": vehicle.get("transmission"),
            "vin": vehicle.get("vin"),
            "license_plate": vehicle.get("license_plate"),
            "color": vehicle.get("color"),
            "current_mileage": vehicle.get("current_mileage"),
            "mileage": vehicle.get("current_mileage"),
            "average_mileage_daily": vehicle.get("average_mileage_daily"),
            "average_mileage_weekly": vehicle.get("average_mileage_weekly"),
            "average_mileage_monthly": vehicle.get("average_mileage_monthly"),
            "engine_hours": vehicle.get("engine_hours"),
            "acquisition_date": vehicle.get("acquisition_date"),
            "usage_type": vehicle.get("usage_type"),
            "driving_conditions": vehicle.get("driving_conditions"),
            "image_urls": vehicle.get("image_urls", []),
            "maintenance_history": vehicle.get("maintenance_history", {}),
            "created_at": vehicle.get("created_at").isoformat() if vehicle.get("created_at") else None,
            "updated_at": vehicle.get("updated_at").isoformat() if vehicle.get("updated_at") else None,
        }
