from datetime import datetime, timezone

from ..utils.db import get_db


class VehicleCatalog:
    collection = "vehicle_catalog"

    @staticmethod
    def upsert_many(items):
        db = get_db()
        now = datetime.now(timezone.utc)
        upserted = 0

        for item in items:
            catalog_id = (item.get("id") or "").strip().lower()
            if not catalog_id:
                continue

            payload = {
                "id": catalog_id,
                "make": item.get("make"),
                "model": item.get("model"),
                "vehicle_type": item.get("vehicle_type"),
                "fuel_type": item.get("fuel_type"),
                "transmission": item.get("transmission"),
                "image_urls": item.get("image_urls", []),
                "updated_at": now,
            }
            result = db[VehicleCatalog.collection].update_one(
                {"id": catalog_id},
                {"$set": payload, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
            if result.upserted_id is not None:
                upserted += 1

        return upserted

    @staticmethod
    def find_all():
        db = get_db()
        rows = db[VehicleCatalog.collection].find({}).sort("make", 1)
        return [VehicleCatalog.serialize(r) for r in rows]

    @staticmethod
    def find_by_id(catalog_id):
        db = get_db()
        row = db[VehicleCatalog.collection].find_one({"id": catalog_id})
        return VehicleCatalog.serialize(row) if row else None

    @staticmethod
    def serialize(row):
        if not row:
            return None
        return {
            "id": row.get("id"),
            "make": row.get("make"),
            "model": row.get("model"),
            "vehicle_type": row.get("vehicle_type"),
            "fuel_type": row.get("fuel_type"),
            "transmission": row.get("transmission"),
            "image_urls": row.get("image_urls", []),
        }
