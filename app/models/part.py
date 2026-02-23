from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from ..utils.db import get_db


class Part:
    collection = "parts"
    updatable_fields = {"name", "category", "make", "year", "model", "compatibility", "price", "quantity"}

    @staticmethod
    def create(user_id, payload):
        db = get_db()
        now = datetime.now(timezone.utc)
        item = {
            "user_id": user_id,
            "name": payload.get("name"),
            "category": payload.get("category"),
            "make": payload.get("make"),
            "year": payload.get("year"),
            "model": payload.get("model"),
            "compatibility": payload.get("compatibility", []),
            "price": payload.get("price"),
            "quantity": payload.get("quantity"),
            "created_at": now,
            "updated_at": now,
        }
        inserted = db[Part.collection].insert_one(item)
        item["_id"] = inserted.inserted_id
        return Part.serialize(item)

    @staticmethod
    def find_filtered(user_id, q="", category="", page=1, limit=20):
        db = get_db()
        query = {"user_id": user_id}
        if q:
            query["$or"] = [
                {"name": {"$regex": q, "$options": "i"}},
                {"make": {"$regex": q, "$options": "i"}},
                {"model": {"$regex": q, "$options": "i"}},
                {"category": {"$regex": q, "$options": "i"}},
                {"compatibility": {"$elemMatch": {"$regex": q, "$options": "i"}}},
            ]
        if category and category != "all":
            query["category"] = category

        total = db[Part.collection].count_documents(query)
        rows = db[Part.collection].find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
        return [Part.serialize(r) for r in rows], total

    @staticmethod
    def find_by_id_for_user(part_id, user_id):
        db = get_db()
        row = db[Part.collection].find_one({"_id": ObjectId(part_id), "user_id": user_id})
        return Part.serialize(row) if row else None

    @staticmethod
    def find_raw_by_id_for_user(part_id, user_id):
        db = get_db()
        return db[Part.collection].find_one({"_id": ObjectId(part_id), "user_id": user_id})

    @staticmethod
    def find_for_order_options(user_id, make="", model="", year=None):
        db = get_db()
        query = {"user_id": user_id}
        if make:
            query["make"] = {"$regex": f"^{make}$", "$options": "i"}
        if model:
            query["$or"] = [
                {"model": {"$regex": f"^{model}$", "$options": "i"}},
                {"compatibility": {"$elemMatch": {"$regex": f"^{model}$", "$options": "i"}}},
            ]
        if year is not None:
            query["year"] = year
        rows = db[Part.collection].find(query).sort("created_at", -1)
        return [Part.serialize(r) for r in rows]

    @staticmethod
    def update_for_user(part_id, user_id, payload):
        db = get_db()
        updates = {k: payload[k] for k in Part.updatable_fields if k in payload}
        if not updates:
            return None
        updates["updated_at"] = datetime.now(timezone.utc)
        row = db[Part.collection].find_one_and_update(
            {"_id": ObjectId(part_id), "user_id": user_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return Part.serialize(row) if row else None

    @staticmethod
    def reserve_stock(part_id, user_id, quantity):
        db = get_db()
        return db[Part.collection].find_one_and_update(
            {"_id": ObjectId(part_id), "user_id": user_id, "quantity": {"$gte": quantity}},
            {"$inc": {"quantity": -quantity}, "$set": {"updated_at": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )

    @staticmethod
    def restore_stock(part_id, user_id, quantity):
        db = get_db()
        db[Part.collection].update_one(
            {"_id": ObjectId(part_id), "user_id": user_id},
            {"$inc": {"quantity": quantity}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    @staticmethod
    def delete_for_user(part_id, user_id):
        db = get_db()
        result = db[Part.collection].delete_one({"_id": ObjectId(part_id), "user_id": user_id})
        return result.deleted_count > 0

    @staticmethod
    def serialize(item):
        if not item:
            return None
        return {
            "id": str(item.get("_id")),
            "user_id": item.get("user_id"),
            "name": item.get("name"),
            "category": item.get("category"),
            "make": item.get("make"),
            "year": item.get("year"),
            "model": item.get("model"),
            "compatibility": item.get("compatibility", []),
            "price": item.get("price"),
            "quantity": item.get("quantity"),
            "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
            "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
        }
