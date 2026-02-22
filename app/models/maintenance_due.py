from datetime import datetime, timezone

from ..utils.db import get_db


class MaintenanceDue:
    collection = "maintenance_due"

    @staticmethod
    def upsert_for_vehicle(user_id, vehicle_id, payload):
        db = get_db()
        now = datetime.now(timezone.utc)
        db[MaintenanceDue.collection].update_one(
            {"user_id": user_id, "vehicle_id": vehicle_id},
            {
                "$set": {
                    "user_id": user_id,
                    "vehicle_id": vehicle_id,
                    "vehicle_label": payload.get("vehicle_label"),
                    "current_mileage": payload.get("current_mileage"),
                    "items": payload.get("items", []),
                    "has_due": payload.get("has_due", False),
                    "has_upcoming": payload.get("has_upcoming", False),
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    @staticmethod
    def list_due_by_user(user_id):
        db = get_db()
        rows = db[MaintenanceDue.collection].find({"user_id": user_id}).sort("updated_at", -1)
        return [MaintenanceDue.serialize(r) for r in rows]

    @staticmethod
    def list_all_due():
        db = get_db()
        rows = db[MaintenanceDue.collection].find({}).sort("updated_at", -1)
        return [MaintenanceDue.serialize(r) for r in rows]

    @staticmethod
    def serialize(row):
        if not row:
            return None
        return {
            "id": str(row.get("_id")),
            "user_id": row.get("user_id"),
            "vehicle_id": row.get("vehicle_id"),
            "vehicle_label": row.get("vehicle_label"),
            "current_mileage": row.get("current_mileage"),
            "items": row.get("items", []),
            "has_due": row.get("has_due", False),
            "has_upcoming": row.get("has_upcoming", False),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
            "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        }
