# CareMyCarAPI

API REST para gestion de vehiculos, mantenimiento, pedidos de refacciones y ordenes de servicio, con recomendaciones y predicciones de mantenimiento.

## Funcionalidades
- Autenticacion con JWT (registro, login, perfil)
- Catalogo de vehiculos y alta rapida por catalogo
- CRUD de vehiculos del usuario
- Historial de mantenimiento y recomendaciones automaticas
- Inventario de refacciones y marketplace
- Ordenes de venta y compras con control de stock
- Ordenes de servicio con cotizacion, estados y reportes PDF
- Prediccion de proximo mantenimiento y costo estimado

## Stack
- Python 3 + Flask
- MongoDB (pymongo)
- Scikit-learn, pandas, numpy (modelos ML)
- ReportLab (PDFs)

## Requisitos
- Python 3.10+
- MongoDB accesible (local o Atlas)

## Configuracion
Crea un archivo `.env` en la raiz del proyecto (ya existe en desarrollo local) con estas variables:
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `MONGO_URI`
- `MONGO_DB_NAME`

Ejemplo:
```bash
SECRET_KEY=dev-secret
JWT_SECRET_KEY=dev-jwt-secret
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=vehicle_maintenance
```

## Instalacion
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecutar
```bash
python run.py
```
La API corre en `http://localhost:5000`.

## Salud
- `GET /health` -> `{ "status": "ok" }`

## Autenticacion
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/profile`

Header requerido para endpoints protegidos:
```bash
Authorization: Bearer <token>
```

## Endpoints principales
### Catalogo
- `POST /api/catalog/vehicles/seed` (usa `data/vehicle_catalog.json` si no hay payload)
- `GET /api/catalog/vehicles`
- `GET /api/catalog/vehicles/<catalog_id>`

### Vehiculos
- `POST /api/vehicles`
- `GET /api/vehicles`
- `GET /api/vehicles/<vehicle_id>`
- `PUT /api/vehicles/<vehicle_id>`
- `DELETE /api/vehicles/<vehicle_id>`

### Mantenimiento
- `POST /api/maintenance`
- `GET /api/maintenance/<vehicle_id>`
- `PUT /api/maintenance/<maintenance_id>`
- `DELETE /api/maintenance/<maintenance_id>`
- `GET /api/maintenance/insights/recommendations/<vehicle_id>`
- `GET /api/maintenance/insights/upcoming`
- `GET /api/maintenance/insights/upcoming/all` (admin)

### Refacciones
- `GET /api/parts/options`
- `POST /api/parts`
- `GET /api/parts`
- `GET /api/parts/<part_id>`
- `PUT /api/parts/<part_id>`
- `DELETE /api/parts/<part_id>`

### Ordenes de venta y marketplace
- `GET /api/orders/options`
- `POST /api/orders`
- `GET /api/orders`
- `GET /api/orders/<order_id>`
- `PUT /api/orders/<order_id>`
- `DELETE /api/orders/<order_id>`
- `GET /api/orders/marketplace/products`
- `POST /api/orders/marketplace/purchase`
- `GET /api/orders/purchases/my`
- `GET /api/orders/sales/daily-report`
- `GET /api/orders/sales/daily-report/pdf`

### Ordenes de servicio
- `POST /api/service-orders`
- `POST /api/service-orders/quote/<vehicle_id>`
- `GET /api/service-orders/my`
- `GET /api/service-orders` (admin)
- `PATCH /api/service-orders/<order_id>/start` (admin)
- `PATCH /api/service-orders/<order_id>/complete` (admin)
- `PATCH /api/service-orders/<order_id>/cancel`
- `GET /api/service-orders/report` (admin, PDF)

### Predicciones
- `POST /api/predict/<vehicle_id>`
- `GET /api/predictions/<vehicle_id>`

## Datos y modelos
- Catalogo de vehiculos: `data/vehicle_catalog.json`
- Costos y compatibilidad: `data/maintenance_costs.csv`
- Intervalos base: `data/maintenance_intervals.json`
- Modelos ML pre-entrenados: `app/ml_model/*.pkl`

Si los modelos no son compatibles o no se pueden cargar, la API usa reglas de respaldo.

## Notas
- Los endpoints marcados como admin requieren que el usuario tenga `role=admin`.
- El token JWT expira en 6 horas.

## Estructura del proyecto
- `app/routes/` endpoints de la API
- `app/models/` acceso a datos
- `app/utils/` validadores, DB y utilidades
- `app/ml_model/` modelos y prediccion
- `data/` archivos de datos de soporte

## Contribucion
1. Crea una rama con prefijo `codex/`.
2. Agrega pruebas si introduces cambios de logica.
3. Abre un PR con descripcion clara.
