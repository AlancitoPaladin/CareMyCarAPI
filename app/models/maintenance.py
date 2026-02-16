from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from ..utils.db import get_db


class Maintenance:
    collection = "maintenance"

    @staticmethod
    def create(user_id, payload):
        db = get_db()
        now = datetime.now(timezone.utc)
        item = {
            "user_id": user_id,
            "vehicle_id": payload.get("vehicle_id"),
            "service_type": payload.get("service_type"),
            "description": payload.get("description"),
            "cost": payload.get("cost"),
            "mileage": payload.get("mileage"),
            "service_date": payload.get("service_date"),
            "created_at": now,
            "updated_at": now,
        }
        inserted = db[Maintenance.collection].insert_one(item)
        item["_id"] = inserted.inserted_id
        return Maintenance.serialize(item)

    @staticmethod
    def find_by_vehicle(user_id, vehicle_id):
        db = get_db()
        items = db[Maintenance.collection].find({"user_id": user_id, "vehicle_id": vehicle_id}).sort("service_date", -1)
        return [Maintenance.serialize(i) for i in items]

    @staticmethod
    def update_for_user(maintenance_id, user_id, payload):
        db = get_db()
        updates = {
            key: payload[key]
            for key in ["service_type", "description", "cost", "mileage", "service_date"]
            if key in payload
        }
        if not updates:
            return None

        updates["updated_at"] = datetime.now(timezone.utc)
        result = db[Maintenance.collection].find_one_and_update(
            {"_id": ObjectId(maintenance_id), "user_id": user_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return Maintenance.serialize(result) if result else None

    @staticmethod
    def delete_for_user(maintenance_id, user_id):
        db = get_db()
        result = db[Maintenance.collection].delete_one({"_id": ObjectId(maintenance_id), "user_id": user_id})
        return result.deleted_count > 0

    @staticmethod
    def serialize(item):
        if not item:
            return None
        return {
            "id": str(item.get("_id")),
            "user_id": item.get("user_id"),
            "vehicle_id": item.get("vehicle_id"),
            "service_type": item.get("service_type"),
            "description": item.get("description"),
            "cost": item.get("cost"),
            "mileage": item.get("mileage"),
            "service_date": item.get("service_date"),
            "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
            "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
        }
