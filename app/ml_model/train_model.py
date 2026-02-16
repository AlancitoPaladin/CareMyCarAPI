from pathlib import Path

try:
    import joblib
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
except Exception as exc:  # pragma: no cover
    joblib = None
    pd = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = Path(__file__).resolve().parent

COST_DATA_PATH = DATA_DIR / "maintenance_costs.csv"
INTERVAL_DATA_PATH = DATA_DIR / "interval_optimization_data.csv"
COST_MODEL_PATH = MODEL_DIR / "cost_model.pkl"
INTERVAL_MODEL_PATH = MODEL_DIR / "interval_model.pkl"


def _build_pipeline(categorical_cols, numeric_cols, estimator):
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
            ("num", "passthrough", numeric_cols),
        ]
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", estimator)])


def train_cost_model():
    df = pd.read_csv(COST_DATA_PATH)

    target_col = "next_maintenance_cost_mxn"
    categorical_cols = ["service_type", "make", "model", "fuel_type", "transmission", "vehicle_type"]
    numeric_cols = [
        "current_mileage",
        "average_mileage_monthly",
        "cylinders",
        "vehicle_age",
        "historical_avg_cost",
    ]

    X = df[categorical_cols + numeric_cols]
    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = _build_pipeline(
        categorical_cols=categorical_cols,
        numeric_cols=numeric_cols,
        estimator=RandomForestRegressor(n_estimators=300, random_state=42),
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))

    bundle = {
        "model": model,
        "model_name": "RandomForestRegressor",
        "mae": mae,
        "categorical_cols": categorical_cols,
        "numeric_cols": numeric_cols,
    }
    joblib.dump(bundle, COST_MODEL_PATH)

    return {
        "model": "cost_regressor",
        "algorithm": "RandomForestRegressor",
        "samples": int(len(df)),
        "mae": round(mae, 2),
        "output_path": str(COST_MODEL_PATH),
    }


def train_interval_model():
    df = pd.read_csv(INTERVAL_DATA_PATH)

    target_col = "recommended_oil_change_interval_km"
    categorical_cols = ["usage_type", "driving_conditions", "fuel_type", "vehicle_type"]
    numeric_cols = ["current_mileage", "average_mileage_monthly", "engine_hours"]

    X = df[categorical_cols + numeric_cols]
    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = _build_pipeline(
        categorical_cols=categorical_cols,
        numeric_cols=numeric_cols,
        estimator=LinearRegression(),
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))

    bundle = {
        "model": model,
        "model_name": "LinearRegression",
        "mae": mae,
        "categorical_cols": categorical_cols,
        "numeric_cols": numeric_cols,
    }
    joblib.dump(bundle, INTERVAL_MODEL_PATH)

    return {
        "model": "interval_optimizer",
        "algorithm": "LinearRegression",
        "samples": int(len(df)),
        "mae": round(mae, 2),
        "output_path": str(INTERVAL_MODEL_PATH),
    }


def train():
    if _IMPORT_ERROR is not None:
        return {
            "status": "error",
            "message": "Missing ML dependencies. Install requirements first.",
            "details": str(_IMPORT_ERROR),
        }

    missing = [str(p) for p in [COST_DATA_PATH, INTERVAL_DATA_PATH] if not p.exists()]
    if missing:
        return {"status": "error", "message": "Missing training data files", "missing": missing}

    cost_result = train_cost_model()
    interval_result = train_interval_model()

    return {
        "status": "ok",
        "results": [cost_result, interval_result],
    }


if __name__ == "__main__":
    print(train())
