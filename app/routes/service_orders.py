import io
import random
from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, request, send_file

from ..ml_model.predict import estimate_next_maintenance_cost
from ..models import Maintenance, ServiceOrder, Vehicle
from ..utils.db import get_db
from ..utils.decorators import token_required
from ..utils.validators import validate_service_order_payload

service_orders_bp = Blueprint("service_orders", __name__)

SERVICE_TYPE_ALIASES = {
    "cambio de aceite": "oil_change",
    "oil change": "oil_change",
    "afinacion": "minor_service",
    "afinação": "minor_service",
    "servicio general": "major_service",
    "general service": "major_service",
    "frenos": "brake_service",
    "brake service": "brake_service",
    "llantas": "tire_service",
    "tire service": "tire_service",
}

SERVICE_PRODUCTS = {
    "oil_change": [
        {"sku": "aceite_5w30", "name": "Aceite 5W30 (4L)", "qty": 1, "unit_price_mxn": 780},
        {"sku": "filtro_aceite", "name": "Filtro de aceite", "qty": 1, "unit_price_mxn": 230},
    ],
    "minor_service": [
        {"sku": "aceite_5w30", "name": "Aceite 5W30 (4L)", "qty": 1, "unit_price_mxn": 780},
        {"sku": "filtro_aceite", "name": "Filtro de aceite", "qty": 1, "unit_price_mxn": 230},
        {"sku": "filtro_aire", "name": "Filtro de aire", "qty": 1, "unit_price_mxn": 310},
    ],
    "major_service": [
        {"sku": "aceite_5w30", "name": "Aceite 5W30 (4L)", "qty": 1, "unit_price_mxn": 780},
        {"sku": "filtro_aceite", "name": "Filtro de aceite", "qty": 1, "unit_price_mxn": 230},
        {"sku": "filtro_aire", "name": "Filtro de aire", "qty": 1, "unit_price_mxn": 310},
        {"sku": "filtro_cabina", "name": "Filtro de cabina", "qty": 1, "unit_price_mxn": 280},
    ],
    "brake_service": [
        {"sku": "balatas_del", "name": "Juego de balatas delanteras", "qty": 1, "unit_price_mxn": 950},
        {"sku": "liq_frenos", "name": "Líquido de frenos", "qty": 1, "unit_price_mxn": 270},
    ],
    "tire_service": [
        {"sku": "valvulas", "name": "Juego de válvulas", "qty": 1, "unit_price_mxn": 120},
        {"sku": "balanceo", "name": "Plomos de balanceo", "qty": 1, "unit_price_mxn": 160},
    ],
}


def _is_admin(user):
    return str(user.get("role", "user")).lower() == "admin"


def _normalize_service_type(raw):
    value = str(raw or "").strip().lower()
    return SERVICE_TYPE_ALIASES.get(value, value.replace(" ", "_") or "major_service")


def _build_quote(vehicle, history, service_type_raw):
    service_key = _normalize_service_type(service_type_raw)
    prediction = estimate_next_maintenance_cost(vehicle, history, service_type=service_key)
    predicted_total = float(prediction.get("estimated_cost_mxn") or 0.0)
    product_items = SERVICE_PRODUCTS.get(service_key, [])
    products_total = sum((line.get("qty", 0) or 0) * (line.get("unit_price_mxn", 0) or 0) for line in product_items)
    labor_total = round(max(predicted_total * 0.35, 350.0), 2)
    suggested_total = round(max(predicted_total, products_total + labor_total), 2)

    return {
        "service_key": service_key,
        "prediction": prediction,
        "products": product_items,
        "products_total_mxn": round(products_total, 2),
        "labor_total_mxn": labor_total,
        "suggested_total_mxn": suggested_total,
    }


def _attach_user_info(rows):
    db = get_db()
    user_ids = [row.get("user_id") for row in rows if row.get("user_id") and ObjectId.is_valid(row.get("user_id"))]
    users = db["users"].find({"_id": {"$in": [ObjectId(uid) for uid in user_ids]}})
    users_by_id = {str(u["_id"]): {"email": u.get("email"), "name": u.get("name")} for u in users}
    for row in rows:
        info = users_by_id.get(row.get("user_id"), {})
        row["user_email"] = info.get("email")
        row["user_name"] = info.get("name")
    return rows


def _create_pdf_report(rows, date_from, date_to):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Reporte de Vehiculos en Servicio")
    y -= 20
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f"Rango: {date_from or 'N/A'} a {date_to or 'N/A'}")
    y -= 22

    headers = ["Fecha", "Cliente", "Vehiculo", "Servicio", "Estado", "Costo final"]
    xs = [40, 110, 220, 330, 430, 500]
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
        snapshot = row.get("vehicle_snapshot", {}) or {}
        vehicle_label = f"{snapshot.get('make', '')} {snapshot.get('model', '')}".strip() or row.get("vehicle_id", "")
        customer = row.get("user_name") or row.get("user_email") or row.get("user_id")
        cols = [
            row.get("scheduled_date") or "",
            str(customer or "")[:20],
            str(vehicle_label)[:22],
            str(row.get("service_type") or "")[:20],
            str(row.get("status") or ""),
            str(row.get("final_cost") or row.get("estimated_cost") or ""),
        ]
        for idx, value in enumerate(cols):
            pdf.drawString(xs[idx], y, value)
        y -= 12

    pdf.save()
    buffer.seek(0)
    return buffer


@service_orders_bp.post("")
@token_required
def create_service_order(current_user):
    payload = request.get_json(silent=True) or {}
    errors = validate_service_order_payload(payload, partial=False)
    if errors:
        return {"errors": errors}, 400

    vehicle_id = payload.get("vehicle_id")
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    vehicle = Vehicle.find_by_id_for_user(vehicle_id, current_user["_id"])
    if not vehicle:
        return {"error": "Vehicle not found"}, 404

    history = Maintenance.find_by_vehicle(current_user["_id"], vehicle_id)
    quote = _build_quote(vehicle, history, payload.get("service_type"))
    completion_token = f"{random.randint(0, 999999):06d}"
    item = ServiceOrder.create(
        {
            "user_id": current_user["_id"],
            "vehicle_id": vehicle_id,
            "vehicle_snapshot": {
                "make": vehicle.get("make"),
                "model": vehicle.get("model"),
                "year": vehicle.get("year"),
            },
            "service_type": payload.get("service_type"),
            "scheduled_date": payload.get("scheduled_date"),
            "status": "PROGRAMADO",
            "estimated_cost": quote["suggested_total_mxn"],
            "predicted_service_type": quote["service_key"],
            "cost_breakdown": {
                "prediction": quote["prediction"],
                "products": quote["products"],
                "products_total_mxn": quote["products_total_mxn"],
                "labor_total_mxn": quote["labor_total_mxn"],
            },
            "user_notes": payload.get("user_notes"),
            "completion_token": completion_token,
        }
    )
    return {"order": item, "quote": quote}, 201


@service_orders_bp.post("/quote/<vehicle_id>")
@token_required
def quote_service_order(current_user, vehicle_id):
    if not ObjectId.is_valid(vehicle_id):
        return {"error": "Invalid vehicle id"}, 400

    vehicle = Vehicle.find_by_id_for_user(vehicle_id, current_user["_id"])
    if not vehicle:
        return {"error": "Vehicle not found"}, 404

    payload = request.get_json(silent=True) or {}
    service_type = payload.get("service_type")
    if not service_type:
        return {"error": "service_type is required"}, 400

    history = Maintenance.find_by_vehicle(current_user["_id"], vehicle_id)
    quote = _build_quote(vehicle, history, service_type)
    return {"vehicle_id": vehicle_id, "service_type": service_type, "quote": quote}, 200


@service_orders_bp.get("/my")
@token_required
def list_my_orders(current_user):
    items = ServiceOrder.find_by_user(current_user["_id"])
    return {"items": items}, 200


@service_orders_bp.get("")
@token_required
def list_all_orders(current_user):
    if not _is_admin(current_user):
        return {"error": "Forbidden"}, 403

    status = (request.args.get("status") or "").strip().upper()
    filters = {}
    if status:
        filters["status"] = status
    items = ServiceOrder.find_all(filters=filters)
    return {"items": _attach_user_info(items)}, 200


@service_orders_bp.patch("/<order_id>/start")
@token_required
def start_service_order(current_user, order_id):
    if not _is_admin(current_user):
        return {"error": "Forbidden"}, 403
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400

    order = ServiceOrder.find_by_id(order_id)
    if not order:
        return {"error": "Order not found"}, 404
    if order.get("status") != "PROGRAMADO":
        return {"error": "Only PROGRAMADO orders can move to EN_PROCESO"}, 409

    payload = request.get_json(silent=True) or {}
    updated = ServiceOrder.update(
        order_id,
        {
            "status": "EN_PROCESO",
            "check_in_at": datetime.now(timezone.utc),
            "agency_notes": payload.get("agency_notes"),
        },
    )
    return {"order": updated}, 200


@service_orders_bp.patch("/<order_id>/complete")
@token_required
def complete_service_order(current_user, order_id):
    if not _is_admin(current_user):
        return {"error": "Forbidden"}, 403
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400

    payload = request.get_json(silent=True) or {}
    errors = validate_service_order_payload(payload, partial=True)
    if errors:
        return {"errors": errors}, 400

    order = ServiceOrder.find_by_id(order_id)
    if not order:
        return {"error": "Order not found"}, 404
    if order.get("status") != "EN_PROCESO":
        return {"error": "Only EN_PROCESO orders can be completed"}, 409

    provided_token = str(payload.get("completion_token") or "").strip()
    if not provided_token or provided_token != str(order.get("completion_token") or ""):
        return {"error": "Invalid completion token"}, 400

    updated = ServiceOrder.update(
        order_id,
        {
            "status": "FINALIZADO",
            "final_cost": payload.get("final_cost") if payload.get("final_cost") is not None else order.get("estimated_cost"),
            "agency_notes": payload.get("agency_notes"),
            "completed_at": datetime.now(timezone.utc),
        },
    )

    # Persist completion into maintenance history
    Maintenance.create(
        order.get("user_id"),
        {
            "vehicle_id": order.get("vehicle_id"),
            "service_type": order.get("service_type"),
            "service_date": datetime.now(timezone.utc).date().isoformat(),
            "description": f"Orden de servicio finalizada ({updated.get('id')})",
            "cost": updated.get("final_cost"),
            "mileage": payload.get("mileage"),
        },
    )

    return {"order": updated}, 200


@service_orders_bp.patch("/<order_id>/cancel")
@token_required
def cancel_service_order(current_user, order_id):
    if not ObjectId.is_valid(order_id):
        return {"error": "Invalid order id"}, 400

    is_admin = _is_admin(current_user)
    order = ServiceOrder.find_by_id(order_id) if is_admin else ServiceOrder.find_by_id_for_user(order_id, current_user["_id"])
    if not order:
        return {"error": "Order not found"}, 404
    if order.get("status") in {"FINALIZADO", "CANCELADO"}:
        return {"error": "Order can not be canceled in current status"}, 409

    payload = request.get_json(silent=True) or {}
    updated = ServiceOrder.update(
        order_id,
        {"status": "CANCELADO", "agency_notes": payload.get("agency_notes")},
    )
    return {"order": updated}, 200


@service_orders_bp.get("/report")
@token_required
def report_service_orders(current_user):
    if not _is_admin(current_user):
        return {"error": "Forbidden"}, 403

    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    status = (request.args.get("status") or "FINALIZADO").strip().upper()

    filters = {"status": status} if status else {}
    rows = ServiceOrder.find_all(filters=filters)
    rows = _attach_user_info(rows)

    if date_from:
        rows = [r for r in rows if (r.get("scheduled_date") or "") >= date_from]
    if date_to:
        rows = [r for r in rows if (r.get("scheduled_date") or "") <= date_to]

    pdf_buffer = _create_pdf_report(rows, date_from, date_to)
    filename = f"service_orders_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)
