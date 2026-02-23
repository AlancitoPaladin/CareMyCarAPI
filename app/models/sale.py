from datetime import datetime, timezone

from bson import ObjectId

from ..utils.db import get_db


class Sale:
    collection = "sales"

    @staticmethod
    def create_from_order(order):
        if not order:
            return None

        db = get_db()
        order_id = order.get("id")
        if not order_id or not ObjectId.is_valid(order_id):
            return None

        existing = db[Sale.collection].find_one({"order_id": order_id})
        if existing:
            return Sale.serialize(existing)

        sold_at = datetime.now(timezone.utc)
        item = {
            "order_id": order_id,
            "user_id": order.get("user_id"),
            "buyer_id": order.get("buyer_id"),
            "client_name": order.get("client_name"),
            "vin": order.get("vin"),
            "make": order.get("make"),
            "year": order.get("year"),
            "model": order.get("model"),
            "part_id": order.get("part_id"),
            "part_name": order.get("part_name"),
            "quantity": order.get("quantity"),
            "unit_price": order.get("unit_price"),
            "total_price": order.get("total_price"),
            "status": "delivered",
            "order_created_at": order.get("created_at"),
            "sold_at": sold_at,
            "created_at": sold_at,
            "updated_at": sold_at,
        }
        inserted = db[Sale.collection].insert_one(item)
        item["_id"] = inserted.inserted_id
        return Sale.serialize(item)

    @staticmethod
    def get_daily_report_for_seller(seller_id, report_date):
        db = get_db()
        day_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc)
        day_end = datetime(
            report_date.year, report_date.month, report_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc
        )

        sales_query = {
            "user_id": seller_id,
            "sold_at": {"$gte": day_start, "$lte": day_end},
        }
        sales_rows = [Sale.serialize(r) for r in db[Sale.collection].find(sales_query).sort("sold_at", -1)]
        total_sales = round(sum(float(r.get("total_price") or 0.0) for r in sales_rows), 2)

        orders_query = {
            "user_id": seller_id,
            "created_at": {"$gte": day_start, "$lte": day_end},
        }
        orders_rows = list(db["orders"].find(orders_query))
        pending = sum(1 for r in orders_rows if str(r.get("status") or "").lower() == "pending")
        confirmed = sum(1 for r in orders_rows if str(r.get("status") or "").lower() == "confirmed")
        canceled = sum(1 for r in orders_rows if str(r.get("status") or "").lower() == "canceled")

        return {
            "date": report_date.isoformat(),
            "total_orders": len(sales_rows),
            "total_sales": total_sales,
            "pending_count": pending,
            "confirmed_count": confirmed,
            "delivered_count": len(sales_rows),
            "canceled_count": canceled,
            "items": sales_rows,
        }

    @staticmethod
    def serialize(item):
        if not item:
            return None
        sold_at = item.get("sold_at")
        created_at = item.get("created_at")
        updated_at = item.get("updated_at")
        return {
            "id": str(item.get("_id")),
            "order_id": item.get("order_id"),
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
            "status": item.get("status") or "delivered",
            "sold_at": sold_at.isoformat() if hasattr(sold_at, "isoformat") else sold_at,
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
            "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
        }
