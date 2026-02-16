import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

VALID_VEHICLE_TYPES = {"sedan", "suv", "pickup", "hatchback", "coupe", "van", "wagon", "other"}
VALID_FUEL_TYPES = {"gasolina", "diesel", "electrico", "hibrido"}
VALID_TRANSMISSION = {"manual", "automatica"}
VALID_USAGE_TYPES = {"ciudad", "carretera", "mixto"}
VALID_DRIVING_CONDITIONS = {"severas", "normales", "suaves"}


def validate_email(email):
    return bool(email and _EMAIL_RE.match(email))


def validate_password(password):
    return bool(password and len(password) >= 8)


def validate_vehicle_payload(payload, partial=False):
    errors = []
    required = ["make", "model", "year", "current_mileage"]

    if not partial:
        for field in required:
            if field not in payload and not (field == "current_mileage" and "mileage" in payload):
                errors.append(f"{field} is required")

    if "year" in payload and not isinstance(payload["year"], int):
        errors.append("year must be integer")

    if "current_mileage" in payload and not isinstance(payload["current_mileage"], int):
        errors.append("current_mileage must be integer")

    if "mileage" in payload and not isinstance(payload["mileage"], int):
        errors.append("mileage must be integer (deprecated, use current_mileage)")

    if "vehicle_type" in payload and str(payload["vehicle_type"]).lower() not in VALID_VEHICLE_TYPES:
        errors.append("vehicle_type must be one of: sedan, suv, pickup, hatchback, coupe, van, wagon, other")

    if "fuel_type" in payload and str(payload["fuel_type"]).lower() not in VALID_FUEL_TYPES:
        errors.append("fuel_type must be one of: gasolina, diesel, electrico, hibrido")

    if "transmission" in payload and str(payload["transmission"]).lower() not in VALID_TRANSMISSION:
        errors.append("transmission must be one of: manual, automatica")

    if "usage_type" in payload and str(payload["usage_type"]).lower() not in VALID_USAGE_TYPES:
        errors.append("usage_type must be one of: ciudad, carretera, mixto")

    if "driving_conditions" in payload and str(payload["driving_conditions"]).lower() not in VALID_DRIVING_CONDITIONS:
        errors.append("driving_conditions must be one of: severas, normales, suaves")

    integer_fields = [
        "cylinders",
        "average_mileage_daily",
        "average_mileage_weekly",
        "average_mileage_monthly",
        "engine_hours",
    ]
    for field in integer_fields:
        if field in payload and not isinstance(payload[field], int):
            errors.append(f"{field} must be integer")

    if "acquisition_date" in payload and not _DATE_RE.match(str(payload["acquisition_date"])):
        errors.append("acquisition_date must use YYYY-MM-DD format")

    if "maintenance_history" in payload and not isinstance(payload["maintenance_history"], dict):
        errors.append("maintenance_history must be an object")

    if isinstance(payload.get("maintenance_history"), dict):
        history = payload["maintenance_history"]
        if "last_oil_change_date" in history and not _DATE_RE.match(str(history["last_oil_change_date"])):
            errors.append("maintenance_history.last_oil_change_date must use YYYY-MM-DD format")

        if "last_oil_change_mileage" in history and not isinstance(history["last_oil_change_mileage"], int):
            errors.append("maintenance_history.last_oil_change_mileage must be integer")

        if "oil_change_interval_km" in history and not isinstance(history["oil_change_interval_km"], int):
            errors.append("maintenance_history.oil_change_interval_km must be integer")

        filter_fields = ["oil", "air", "fuel", "cabin"]
        for ff in filter_fields:
            if ff in history.get("filters", {}):
                entry = history["filters"][ff]
                if not isinstance(entry, dict):
                    errors.append(f"maintenance_history.filters.{ff} must be an object")
                    continue
                if "date" in entry and not _DATE_RE.match(str(entry["date"])):
                    errors.append(f"maintenance_history.filters.{ff}.date must use YYYY-MM-DD format")
                if "km" in entry and not isinstance(entry["km"], int):
                    errors.append(f"maintenance_history.filters.{ff}.km must be integer")

        tires = history.get("tires")
        if tires is not None:
            if not isinstance(tires, dict):
                errors.append("maintenance_history.tires must be an object")
            else:
                date_fields = [
                    "last_rotation_date",
                    "last_balancing_date",
                    "last_alignment_date",
                    "purchase_date",
                ]
                for df in date_fields:
                    if df in tires and not _DATE_RE.match(str(tires[df])):
                        errors.append(f"maintenance_history.tires.{df} must use YYYY-MM-DD format")

                numeric_fields = ["tread_depth_mm", "tire_pressure_psi"]
                for nf in numeric_fields:
                    if nf in tires and not isinstance(tires[nf], (int, float)):
                        errors.append(f"maintenance_history.tires.{nf} must be numeric")

        brakes = history.get("brakes")
        if brakes is not None:
            if not isinstance(brakes, dict):
                errors.append("maintenance_history.brakes must be an object")
            else:
                date_fields = ["last_change_date", "fluid_bleed_date"]
                for df in date_fields:
                    if df in brakes and not _DATE_RE.match(str(brakes[df])):
                        errors.append(f"maintenance_history.brakes.{df} must use YYYY-MM-DD format")

                numeric_fields = ["front_pad_thickness_mm", "rear_pad_thickness_mm", "brake_fluid_level_percent"]
                for nf in numeric_fields:
                    if nf in brakes and not isinstance(brakes[nf], (int, float)):
                        errors.append(f"maintenance_history.brakes.{nf} must be numeric")

    return errors


def validate_maintenance_payload(payload, partial=False):
    errors = []
    required = ["vehicle_id", "service_type", "service_date"]

    if not partial:
        for field in required:
            if field not in payload:
                errors.append(f"{field} is required")

    if "cost" in payload and not isinstance(payload["cost"], (int, float)):
        errors.append("cost must be numeric")

    if "mileage" in payload and not isinstance(payload["mileage"], int):
        errors.append("mileage must be integer")

    return errors
