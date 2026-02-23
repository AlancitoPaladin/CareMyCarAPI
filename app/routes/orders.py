import csv
import io
from datetime import datetime, date
from pathlib import Path

from bson import ObjectId
from flask import Blueprint, request, send_file

from ..models import Order, Part, Sale
from ..utils.db import get_db
from ..utils.decorators import token_required

orders_bp = Blueprint("orders", __name__)

VALID_ORDER_STATUS = {"pending", "confirmed", "delivered", "canceled"}
ORDER_ALLOWED_TRANSITIONS = {
    "pending": {"confirmed", "canceled"},
    "confirmed": {"delivered", "canceled"},
    "delivered": set(),
    "canceled": set(),
}


def _load_make_model_options():
    file_path = Path(__file__).resolve().parents[2] / "data" / "maintenance_costs.csv"
    if not file_path.exists():
        return []

    options = []
    with file_path.open("r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            make = str(row.get("make") or "").strip()
            model = str(row.get("model") or "").strip()
            if not make or not model:
                continue
            options.append({"make": make, "model": model})
    return options


def _get_agency_user_ids():
    db = get_db()
    rows = db["users"].find({"role": "admin"}, {"_id": 1})
    return [str(r["_id"]) for r in rows]


def _create_sales_pdf_report(report):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    rows = report.get("items") or []
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Reporte Diario de Ventas Concretadas")
    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f"Fecha: {report.get('date') or 'N/A'}")
    y -= 14
    pdf.drawString(40, y, f"Total ventas: ${report.get('total_sales') or 0.0}")
    y -= 14
    pdf.drawString(40, y, f"Ventas concretadas: {report.get('delivered_count') or 0}")
    y -= 22

    headers = ["Hora", "Cliente", "Producto", "Cantidad", "Total"]
    xs = [40, 110, 250, 460, 520]
    pdf.setFont("Helvetica-Bold", 9)
    for idx, header in enumerate(headers):
        pdf.drawString(xs[idx], y, header)
    y -= 12
    pdf.line(40, y, width - 40, y)
    y -= 12
    pdf.setFont("Helvetica", 8)

    for row in rows:
        if y < 60:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica", 8)
        sold_at = str(row.get("sold_at") or "")[:19].replace("T", " ")
        cols = [
            sold_at[11:16] if len(sold_at) >= 16 else "",
            str(row.get("client_name") or "")[:22],
            str(row.get("part_name") or "")[:34],
            str(row.get("quantity") or 0),
            str(row.get("total_price") or 0.0),
        ]
        for idx, value in enumerate(cols):
            pdf.drawString(xs[idx], y, value)
        y -= 12

    pdf.save()
    buffer.seek(0)
    return buffer


@orders_bp.get("/options")
@token_required
def orders_options(current_user):
    make = (request.args.get("make") or "").strip().lower()
    model = (request.args.get("model") or "").strip().lower()
    year = request.args.get("year")

    options = _load_make_model_options()
    makes = sorted({row["make"] for row in options})
    filtered_options = options
    if make:
        filtered_options = [row for row in filtered_options if row["make"].strip().lower() == make]
    models = sorted({row["model"] for row in filtered_options})
    years = list(range(datetime.utcnow().year + 1, 1979, -1))

    filter_year = None
    if year:
        try:
            filter_year = int(year)
        except (TypeError, ValueError):
            return {"error": "year must be integer"}, 400

    part_rows = Part.find_for_order_options(current_user["_id"], make=make, model=model, year=filter_year)
    parts = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "category": p.get("category"),
            "make": p.get("make"),
            "model": p.get("model"),
            "year": p.get("year"),
            "price": p.get("price"),
            "available_quantity": p.get("quantity", 0),
        }
        for p in part_rows
    ]
    return {"years": years, "makes": makes, "models": models, "parts": parts}, 200


@orders_bp.get("/marketplace/products")
@token_required
def list_marketplace_products(current_user):
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(100, int(request.args.get("limit", 20))))
    except ValueError:
        return {"error": "page/limit must be integer"}, 400

    agency_ids = _get_agency_user_ids()
    rows, total = Part.find_marketplace_filtered(
        agency_user_ids=agency_ids,
        q=q,
        category=category,
        page=page,
        limit=limit,
    )
    return {"items": rows, "total": total, "page": page, "limit": limit}, 200


@orders_bp.post("/marketplace/purchase")
@token_required
def purchase_marketplace_product(current_user):
    payload = request.get_json(silent=True) or {}
    part_id = payload.get("part_id")
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400
    try:
        quantity = int(payload.get("quantity", 1))
    except (TypeError, ValueError):
        return {"error": "quantity must be integer"}, 400
    if quantity <= 0:
        return {"error": "quantity must be > 0"}, 400

    raw_part = Part.find_raw_by_id(part_id)
    if not raw_part:
        return {"error": "Part not found"}, 404

    seller_id = str(raw_part.get("user_id") or "")
    if seller_id == current_user["_id"]:
        return {"error": "You can not buy your own product"}, 400

    updated_part = Part.reserve_stock(part_id, seller_id, quantity)
    if not updated_part:
        return {"error": "insufficient stock"}, 400

    make = str(updated_part.get("make") or "N/A").strip() or "N/A"
    model = str(updated_part.get("model") or "N/A").strip() or "N/A"
    year = int(updated_part.get("year") or datetime.utcnow().year)
    unit_price = float(updated_part.get("price") or 0.0)
    buyer_name = (current_user.get("name") or current_user.get("email") or "Cliente").strip()
    buyer_vin = str(payload.get("vin") or f"BUY-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}").strip().upper()

    created = Order.create(
        {
            "user_id": seller_id,
            "buyer_id": current_user["_id"],
            "client_name": buyer_name,
            "vin": buyer_vin,
            "make": make,
            "year": year,
            "model": model,
            "part_id": part_id,
            "part_name": updated_part.get("name"),
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": round(unit_price * quantity, 2),
            "status": "pending",
        }
    )
    return {"order": created}, 201


@orders_bp.get("/purchases/my")
@token_required
def list_my_purchases(current_user):
    status = (request.args.get("status") or "").strip().lower()
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(100, int(request.args.get("limit", 20))))
    except ValueError:
        return {"error": "page/limit must be integer"}, 400

    if status and status != "all" and status not in VALID_ORDER_STATUS:
        return {"error": "invalid status"}, 400

    rows, total = Order.find_purchases_by_buyer(current_user["_id"], status=status, page=page, limit=limit)
    return {"items": rows, "total": total, "page": page, "limit": limit}, 200


@orders_bp.get("/sales/daily-report")
@token_required
def sales_daily_report(current_user):
    date_raw = (request.args.get("date") or "").strip()
    if date_raw:
        try:
            report_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "date must use YYYY-MM-DD format"}, 400
    else:
        report_date = date.today()

    report = Sale.get_daily_report_for_seller(current_user["_id"], report_date)
    return {"report": report}, 200


@orders_bp.get("/sales/daily-report/pdf")
@token_required
def sales_daily_report_pdf(current_user):
    date_raw = (request.args.get("date") or "").strip()
    if date_raw:
        try:
            report_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "date must use YYYY-MM-DD format"}, 400
    else:
        report_date = date.today()

    report = Sale.get_daily_report_for_seller(current_user["_id"], report_date)
    pdf_buffer = _create_sales_pdf_report(report)
    filename = f"sales_daily_report_{report_date.isoformat()}.pdf"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


@orders_bp.post("")
@token_required
def create_order(current_user):
    payload = request.get_json(silent=True) or {}
    required = ["client_name", "vin", "make", "year", "model", "part_id", "quantity"]
    errors = [f"{f} is required" for f in required if f not in payload]
    if errors:
        return {"errors": errors}, 400

    part_id = payload.get("part_id")
    if not ObjectId.is_valid(part_id):
        return {"error": "Invalid part id"}, 400

    try:
        quantity = int(payload.get("quantity"))
        year = int(payload.get("year"))
    except (TypeError, ValueError):
        return {"error": "quantity/year types are invalid"}, 400
    if quantity <= 0:
        return {"error": "quantity must be > 0"}, 400
    make = str(payload.get("make") or "").strip()
    if not make:
        return {"error": "make must not be empty"}, 400
    model = str(payload.get("model") or "").strip()
    if not model:
        return {"error": "model must not be empty"}, 400

    valid_options = _load_make_model_options()
    if valid_options:
        valid_pair = any(
            row["make"].strip().lower() == make.lower() and row["model"].strip().lower() == model.lower()
            for row in valid_options
        )
        if not valid_pair:
            return {"error": "make/model not available in maintenance_costs dataset"}, 400

    part = Part.find_raw_by_id_for_user(part_id, current_user["_id"])
    if not part:
        return {"error": "Part not found"}, 404
    if str(part.get("make") or "").strip().lower() != make.lower() or str(part.get("model") or "").strip().lower() != model.lower():
        return {"error": "selected part does not match make/model"}, 400

    updated_part = Part.reserve_stock(part_id, current_user["_id"], quantity)
    if not updated_part:
        return {"error": "insufficient stock"}, 400

    unit_price = float(updated_part.get("price") or 0.0)
    requested_status = str(payload.get("status") or "pending").strip().lower()
    if requested_status not in {"pending"}:
        return {"error": "initial status must be pending"}, 400

    order = {
        "user_id": current_user["_id"],
        "client_name": str(payload.get("client_name") or "").strip(),
        "vin": str(payload.get("vin") or "").strip().upper(),
        "make": make,
        "year": year,
        "model": model,
        "part_id": part_id,
        "part_name": updated_part.get("name"),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": round(unit_price * quantity, 2),
        "status": "pending",
    }

    created = Order.create(order)
    return {"order": created}, 201


@orders_bp.get("")
@token_required
def list_orders(current_user):
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip().lower()
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(100, int(request.args.get("limit", 20))))
    except ValueError:
        return {"error": "page/limit must be integer"}, 400

    if status and status != "all" and status not in VALID_ORDER_STATUS:
        return {"error": "invalid status"}, 400

    rows, total, all_count, pending_count = Order.find_filtered(
        current_user["_id"],
        q=q,
        status=status,
        page=page,
        limit=limit,
    )
    return {
        "items": rows,
        "page": page,
        "limit": limit,
        "total": total,
        "all_count": all_count,
        "pending_count": pending_count,
    }, 200


@orders_bp.get("/<order_id>")
@token_required
def get_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    row = Order.find_by_id_for_user(order_id, current_user["_id"])
    if not row:
        return {"error": "Order not found"}, 404
    return {"order": row}, 200


@orders_bp.put("/<order_id>")
@token_required
def update_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    current = Order.find_by_id_for_user(order_id, current_user["_id"])
    if not current:
        return {"error": "Order not found"}, 404

    payload = request.get_json(silent=True) or {}
    allowed = {"client_name", "vin", "make", "year", "model", "status"}
    updates = {k: payload[k] for k in allowed if k in payload}
    if not updates:
        return {"error": "empty payload"}, 400

    should_record_sale = False
    if "status" in updates:
        updates["status"] = str(updates["status"]).strip().lower()
        if updates["status"] not in VALID_ORDER_STATUS:
            return {"error": "invalid status"}, 400
        current_status = str(current.get("status") or "pending").strip().lower()
        next_status = updates["status"]
        if next_status != current_status:
            allowed_next = ORDER_ALLOWED_TRANSITIONS.get(current_status, set())
            if next_status not in allowed_next:
                return {"error": f"invalid status transition: {current_status} -> {next_status}"}, 409
            should_record_sale = next_status == "delivered"
    if "year" in updates:
        try:
            updates["year"] = int(updates["year"])
        except (TypeError, ValueError):
            return {"error": "year must be integer"}, 400
    if "vin" in updates:
        updates["vin"] = str(updates["vin"]).strip().upper()
    if "make" in updates:
        updates["make"] = str(updates["make"]).strip()
        if not updates["make"]:
            return {"error": "make must not be empty"}, 400
    if "model" in updates:
        updates["model"] = str(updates["model"]).strip()
        if not updates["model"]:
            return {"error": "model must not be empty"}, 400
    if "make" in updates or "model" in updates:
        current_make = updates.get("make", current.get("make"))
        current_model = updates.get("model", current.get("model"))
        valid_options = _load_make_model_options()
        if valid_options:
            valid_pair = any(
                row["make"].strip().lower() == str(current_make).strip().lower()
                and row["model"].strip().lower() == str(current_model).strip().lower()
                for row in valid_options
            )
            if not valid_pair:
                return {"error": "make/model not available in maintenance_costs dataset"}, 400

    row = Order.update_for_user(order_id, current_user["_id"], updates)
    if not row:
        return {"error": "Order not found"}, 404

    if should_record_sale:
        Sale.create_from_order(row)

    return {"order": row}, 200


@orders_bp.delete("/<order_id>")
@token_required
def delete_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400
    order = Order.find_by_id_for_user(order_id, current_user["_id"])
    if not order:
        return {"error": "Order not found"}, 404

    deleted = Order.delete_for_user(order_id, current_user["_id"])
    if not deleted:
        return {"error": "Order not found"}, 404

    part_id = order.get("part_id")
    quantity = int(order.get("quantity") or 0)
    if ObjectId.is_valid(part_id) and quantity > 0:
        Part.restore_stock(part_id, current_user["_id"], quantity)

    return {"status": "deleted"}, 200
