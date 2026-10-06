# Geospatial File Measurement API: Build Plan

## 1. Goal
Build a production-quality backend service with FastAPI that accepts a geospatial file (.zip containing a Shapefile, or a .kml), extracts every feature, calculates measurements (polygon area, linestring length) in a correct projected CRS, stores the results, and exposes them through a REST API.

## 2. Tech stack
- Framework: FastAPI + Uvicorn
- Python: 3.11+
- Geo IO: pyogrio (via geopandas), fallback to pyshp/fastkml if GDAL driver unavailable
- Geometry: shapely 2.x
- CRS: pyproj
- DB: SQLAlchemy 2.0 + SQLite
- Validation: Pydantic v2 + pydantic-settings
- Tests: pytest, httpx (TestClient)
- Lint/format: ruff
- Packaging: requirements.txt plus requirements-dev.txt, Dockerfile

## 3. Project structure
geo-measurement-api/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── files.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── storage.py
│   │   ├── reader.py
│   │   ├── crs.py
│   │   ├── measurement.py
│   │   └── processing.py
│   └── core/
│       ├── __init__.py
│       └── errors.py
├── tests/
│   ├── conftest.py
│   ├── test_upload_api.py
│   ├── test_file_info_api.py
│   ├── test_measurements_api.py
│   ├── test_reader.py
│   ├── test_crs.py
│   ├── test_measurement.py
│   └── test_storage_security.py
├── sample_data/
├── README.md
├── PLAN.md
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .gitignore
└── Dockerfile
