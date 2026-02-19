from .auth import auth_bp
from .catalog import catalog_bp
from .maintenance import maintenance_bp
from .predictions import predictions_bp
from .vehicles import vehicles_bp

__all__ = ["auth_bp", "catalog_bp", "vehicles_bp", "maintenance_bp", "predictions_bp"]
