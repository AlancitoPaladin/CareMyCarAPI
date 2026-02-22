from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from ..utils.db import get_db


class ServiceOrder:
    collection = "service_orders"

    @staticmethod
    def create(payload):
        db = get_db()
        now = datetime.now(timezone.utc)
        item = {
            "user_id": payload.get("user_id"),
            "vehicle_id": payload.get("vehicle_id"),
            "vehicle_snapshot": payload.get("vehicle_snapshot", {}),
            "service_type": payload.get("service_type"),
            "scheduled_date": payload.get("scheduled_date"),
            "status": payload.get("status", "PROGRAMADO"),
            "estimated_cost": payload.get("estimated_cost"),
            "final_cost": payload.get("final_cost"),
            "predicted_service_type": payload.get("predicted_service_type"),
            "cost_breakdown": payload.get("cost_breakdown"),
            "user_notes": payload.get("user_notes"),
            "agency_notes": payload.get("agency_notes"),
            "completion_token": payload.get("completion_token"),
            "check_in_at": payload.get("check_in_at"),
            "completed_at": payload.get("completed_at"),
            "created_at": now,
            "updated_at": now,
        }
        inserted = db[ServiceOrder.collection].insert_one(item)
        item["_id"] = inserted.inserted_id
        return ServiceOrder.serialize(item)

    @staticmethod
    def find_by_id(order_id):
        db = get_db()
        item = db[ServiceOrder.collection].find_one({"_id": ObjectId(order_id)})
        return ServiceOrder.serialize(item) if item else None

    @staticmethod
    def find_by_id_for_user(order_id, user_id):
        db = get_db()
        item = db[ServiceOrder.collection].find_one({"_id": ObjectId(order_id), "user_id": user_id})
        return ServiceOrder.serialize(item) if item else None

    @staticmethod
    def find_by_user(user_id):
        db = get_db()
        rows = db[ServiceOrder.collection].find({"user_id": user_id}).sort("created_at", -1)
        return [ServiceOrder.serialize(r) for r in rows]

    @staticmethod
    def find_all(filters=None):
        db = get_db()
        query = filters or {}
        rows = db[ServiceOrder.collection].find(query).sort("created_at", -1)
        return [ServiceOrder.serialize(r) for r in rows]

    @staticmethod
    def update(order_id, updates):
        if not updates:
            return None
        db = get_db()
        updates["updated_at"] = datetime.now(timezone.utc)
        row = db[ServiceOrder.collection].find_one_and_update(
            {"_id": ObjectId(order_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return ServiceOrder.serialize(row) if row else None

    @staticmethod
    def serialize(item):
        if not item:
            return None

        def _fmt(value):
            return value.isoformat() if isinstance(value, datetime) else value

        return {
            "id": str(item.get("_id")),
            "user_id": item.get("user_id"),
            "vehicle_id": item.get("vehicle_id"),
            "vehicle_snapshot": item.get("vehicle_snapshot", {}),
            "service_type": item.get("service_type"),
            "scheduled_date": item.get("scheduled_date"),
            "status": item.get("status"),
            "estimated_cost": item.get("estimated_cost"),
            "final_cost": item.get("final_cost"),
            "predicted_service_type": item.get("predicted_service_type"),
            "cost_breakdown": item.get("cost_breakdown"),
            "user_notes": item.get("user_notes"),
            "agency_notes": item.get("agency_notes"),
            "completion_token": item.get("completion_token"),
            "check_in_at": _fmt(item.get("check_in_at")),
            "completed_at": _fmt(item.get("completed_at")),
            "created_at": _fmt(item.get("created_at")),
            "updated_at": _fmt(item.get("updated_at")),
        }
