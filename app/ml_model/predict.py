import json
from datetime import datetime, timedelta
from pathlib import Path

try:
    import joblib
except Exception:  # pragma: no cover - optional dependency at runtime
    joblib = None

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional dependency at runtime
    pd = None


DEFAULT_INTERVALS = {
    "oil_change_km": 10000,
    "general_check_days": 180,
}

DEFAULT_SERVICE_COSTS_MXN = {
    "oil_change": 1400,
    "minor_service": 3200,
    "major_service": 8500,
    "brake_service": 4200,
    "tire_service": 2600,
}

COST_MODEL_PATH = Path(__file__).resolve().with_name("cost_model.pkl")
INTERVAL_MODEL_PATH = Path(__file__).resolve().with_name("interval_model.pkl")


def load_intervals():
    data_file = Path(__file__).resolve().parents[2] / "data" / "maintenance_intervals.json"
    if not data_file.exists():
        return DEFAULT_INTERVALS

    with data_file.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    return {**DEFAULT_INTERVALS, **loaded}


def _load_model(path):
    if joblib is None or not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _history_avg_cost(history):
    costs = [_safe_float(h.get("cost"), default=None) for h in history]
    costs = [c for c in costs if c is not None and c > 0]
    if not costs:
        return 0.0
    return sum(costs) / len(costs)


def _build_cost_features(vehicle, history, service_type):
    current_year = datetime.utcnow().year
    vehicle_year = _safe_int(vehicle.get("year"), default=current_year)
    vehicle_age = max(0, current_year - vehicle_year)

    return {
        "service_type": service_type,
        "make": vehicle.get("make") or "unknown",
        "model": vehicle.get("model") or "unknown",
        "fuel_type": vehicle.get("fuel_type") or "unknown",
        "transmission": vehicle.get("transmission") or "unknown",
        "vehicle_type": vehicle.get("vehicle_type") or "unknown",
        "current_mileage": _safe_int(vehicle.get("current_mileage", vehicle.get("mileage", 0))),
        "average_mileage_monthly": _safe_int(vehicle.get("average_mileage_monthly", 0)),
        "cylinders": _safe_int(vehicle.get("cylinders", 0)),
        "vehicle_age": vehicle_age,
        "historical_avg_cost": _history_avg_cost(history),
    }


def _build_interval_features(vehicle):
    return {
        "usage_type": vehicle.get("usage_type") or "mixto",
        "driving_conditions": vehicle.get("driving_conditions") or "normales",
        "fuel_type": vehicle.get("fuel_type") or "gasolina",
        "vehicle_type": vehicle.get("vehicle_type") or "sedan",
        "current_mileage": _safe_int(vehicle.get("current_mileage", vehicle.get("mileage", 0))),
        "average_mileage_monthly": _safe_int(vehicle.get("average_mileage_monthly", 0)),
        "engine_hours": _safe_int(vehicle.get("engine_hours", 0)),
    }


def estimate_next_maintenance_cost(vehicle, history, service_type="major_service"):
    service_type = service_type or "major_service"
    features = _build_cost_features(vehicle, history, service_type)
    model_bundle = _load_model(COST_MODEL_PATH)

    if model_bundle and pd is not None:
        model = model_bundle.get("model")
        if model is not None:
            frame = pd.DataFrame([features])
            estimate = float(model.predict(frame)[0])
            return {
                "estimated_cost_mxn": round(max(estimate, 500.0), 2),
                "service_type": service_type,
                "model_used": model_bundle.get("model_name", "trained_regressor"),
            }

    base_cost = DEFAULT_SERVICE_COSTS_MXN.get(service_type, DEFAULT_SERVICE_COSTS_MXN["major_service"])
    mileage_factor = 1 + min(features["current_mileage"], 300000) / 300000
    age_factor = 1 + min(features["vehicle_age"], 25) * 0.015
    usage_factor = 1.12 if (vehicle.get("usage_type") == "ciudad" and vehicle.get("driving_conditions") == "severas") else 1.0

    historical = features["historical_avg_cost"]
    blended_base = base_cost if historical <= 0 else (0.7 * base_cost + 0.3 * historical)
    estimate = blended_base * mileage_factor * age_factor * usage_factor

    return {
        "estimated_cost_mxn": round(estimate, 2),
        "service_type": service_type,
        "model_used": "rule_based_fallback",
    }


def optimize_oil_change_interval(vehicle, default_interval_km=10000):
    features = _build_interval_features(vehicle)
    model_bundle = _load_model(INTERVAL_MODEL_PATH)

    if model_bundle and pd is not None:
        model = model_bundle.get("model")
        if model is not None:
            frame = pd.DataFrame([features])
            km = int(round(float(model.predict(frame)[0])))
            km = max(4000, min(15000, km))
            reason = "Intervalo personalizado por modelo entrenado"
            if features["usage_type"] == "ciudad":
                reason += " y uso urbano"
            return {
                "recommended_oil_change_interval_km": km,
                "model_used": model_bundle.get("model_name", "trained_interval_model"),
                "reason": reason,
            }

    usage_penalty = 0
    if features["usage_type"] == "ciudad":
        usage_penalty += 1200
    if features["driving_conditions"] == "severas":
        usage_penalty += 1800

    mileage_penalty = 800 if features["current_mileage"] > 120000 else 0
    monthly_penalty = 700 if features["average_mileage_monthly"] > 2500 else 0

    recommended = max(5000, min(12000, default_interval_km - usage_penalty - mileage_penalty - monthly_penalty))

    return {
        "recommended_oil_change_interval_km": recommended,
        "model_used": "rule_based_fallback",
        "reason": "Intervalo ajustado por patrón de uso y condiciones",
    }


def predict_next_maintenance(vehicle, history, intervals):
    mileage = _safe_int(vehicle.get("current_mileage", vehicle.get("mileage", 0)))
    last_service = history[0] if history else None

    oil_interval = int(intervals.get("oil_change_km", 10000))
    days_interval = int(intervals.get("general_check_days", 180))

    interval_optimization = optimize_oil_change_interval(vehicle, default_interval_km=oil_interval)
    optimized_oil_interval = interval_optimization["recommended_oil_change_interval_km"]

    next_oil_km = mileage + optimized_oil_interval
    if last_service and last_service.get("service_date"):
        base_date = datetime.fromisoformat(last_service["service_date"])
    else:
        base_date = datetime.utcnow()

    next_check = base_date + timedelta(days=days_interval)

    return {
        "recommended_next_oil_change_km": next_oil_km,
        "recommended_general_check_date": next_check.date().isoformat(),
        "optimized_oil_interval": interval_optimization,
        "confidence": 0.72,
        "notes": "Prediccion base con intervalo personalizado.",
    }
