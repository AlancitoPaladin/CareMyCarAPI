from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from ..utils.db import get_db


class Order:
    collection = "orders"
    updatable_fields = {"client_name", "vin", "make", "year", "model", "status"}

    @staticmethod
    def create(payload):
        db = get_db()
        now = datetime.now(timezone.utc)
        item = {
            "user_id": payload.get("user_id"),
            "buyer_id": payload.get("buyer_id"),
            "client_name": payload.get("client_name"),
            "vin": payload.get("vin"),
            "make": payload.get("make"),
            "year": payload.get("year"),
            "model": payload.get("model"),
            "part_id": payload.get("part_id"),
            "part_name": payload.get("part_name"),
            "quantity": payload.get("quantity"),
            "unit_price": payload.get("unit_price"),
            "total_price": payload.get("total_price"),
            "status": payload.get("status", "pending"),
            "created_at": now,
            "updated_at": now,
        }
        inserted = db[Order.collection].insert_one(item)
        item["_id"] = inserted.inserted_id
        return Order.serialize(item)

    @staticmethod
    def find_filtered(user_id, q="", status="", page=1, limit=20):
        db = get_db()
        query_base = {"user_id": user_id}
        if q:
            query_base["$or"] = [
                {"client_name": {"$regex": q, "$options": "i"}},
                {"part_name": {"$regex": q, "$options": "i"}},
                {"vin": {"$regex": q, "$options": "i"}},
                {"make": {"$regex": q, "$options": "i"}},
                {"model": {"$regex": q, "$options": "i"}},
            ]

        query = dict(query_base)
        if status and status != "all":
            query["status"] = status

        total = db[Order.collection].count_documents(query)
        all_count = db[Order.collection].count_documents(query_base)
        pending_count = db[Order.collection].count_documents({**query_base, "status": "pending"})
        rows = db[Order.collection].find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
        return [Order.serialize(r) for r in rows], total, all_count, pending_count

    @staticmethod
    def find_by_id_for_user(order_id, user_id):
        db = get_db()
        row = db[Order.collection].find_one({"_id": ObjectId(order_id), "user_id": user_id})
        return Order.serialize(row) if row else None

    @staticmethod
    def find_purchases_by_buyer(buyer_id, status="", page=1, limit=20):
        db = get_db()
        query = {"buyer_id": buyer_id}
        if status and status != "all":
            query["status"] = status

        total = db[Order.collection].count_documents(query)
        rows = db[Order.collection].find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
        return [Order.serialize(r) for r in rows], total

    @staticmethod
    def get_daily_report_for_seller(seller_id, report_date):
        db = get_db()
        day_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc)
        day_end = datetime(
            report_date.year, report_date.month, report_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc
        )
        query = {
            "user_id": seller_id,
            "created_at": {"$gte": day_start, "$lte": day_end},
        }
        rows = [Order.serialize(r) for r in db[Order.collection].find(query).sort("created_at", -1)]

        total_sales = sum(float(r.get("total_price") or 0.0) for r in rows)
        total_orders = len(rows)
        pending = sum(1 for r in rows if r.get("status") == "pending")
        confirmed = sum(1 for r in rows if r.get("status") == "confirmed")
        delivered = sum(1 for r in rows if r.get("status") == "delivered")
        canceled = sum(1 for r in rows if r.get("status") == "canceled")

        return {
            "date": report_date.isoformat(),
            "total_orders": total_orders,
            "total_sales": round(total_sales, 2),
            "pending_count": pending,
            "confirmed_count": confirmed,
            "delivered_count": delivered,
            "canceled_count": canceled,
            "items": rows,
        }

    @staticmethod
    def update_for_user(order_id, user_id, payload):
        db = get_db()
        updates = {k: payload[k] for k in Order.updatable_fields if k in payload}
        if not updates:
            return None
        updates["updated_at"] = datetime.now(timezone.utc)
        row = db[Order.collection].find_one_and_update(
            {"_id": ObjectId(order_id), "user_id": user_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return Order.serialize(row) if row else None

    @staticmethod
    def delete_for_user(order_id, user_id):
        db = get_db()
        result = db[Order.collection].delete_one({"_id": ObjectId(order_id), "user_id": user_id})
        return result.deleted_count > 0

    @staticmethod
    def serialize(item):
        if not item:
            return None
        return {
            "id": str(item.get("_id")),
            "user_id": item.get("user_id"),
            "buyer_id": item.get("buyer_id"),
            "client_name": item.get("client_name"),
            "vin": item.get("vin"),
            "make": item.get("make"),
            "year": item.get("year"),
            "model": item.get("model"),
            "part_id": item.get("part_id"),
            "part_name": item.get("part_name"),
            "quantity": item.get("quantity"),
            "unit_price": item.get("unit_price"),
            "total_price": item.get("total_price"),
            "status": item.get("status"),
            "created_at": item.get("created_at").isoformat() if item.get("created_at") else None,
            "updated_at": item.get("updated_at").isoformat() if item.get("updated_at") else None,
        }
