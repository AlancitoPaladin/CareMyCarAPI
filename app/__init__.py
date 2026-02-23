from flask import Flask

from .config import DevelopmentConfig
from .routes import (
    auth_bp,
    catalog_bp,
    maintenance_bp,
    orders_bp,
    parts_bp,
    predictions_bp,
    service_orders_bp,
    vehicles_bp,
)
from .utils.db import init_db


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or DevelopmentConfig)

    init_db(app)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(catalog_bp, url_prefix="/api/catalog")
    app.register_blueprint(vehicles_bp, url_prefix="/api/vehicles")
    app.register_blueprint(maintenance_bp, url_prefix="/api/maintenance")
    app.register_blueprint(parts_bp, url_prefix="/api/parts")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(service_orders_bp, url_prefix="/api/service-orders")
    app.register_blueprint(predictions_bp, url_prefix="/api")

    @app.get("/health")
    def health_check():
        return {"status": "ok"}, 200

    return app
