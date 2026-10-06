import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import settings


def test_upload_missing_file(client: TestClient) -> None:
    """POST /api/files/ without a file parameter returns 400 NO_FILE."""
    response = client.post("/api/files/")
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NO_FILE"


def test_upload_unsupported_extension(client: TestClient) -> None:
    """POST /api/files/ with unsupported file extension returns 400 UNSUPPORTED_FILE_TYPE."""
    files = {
        "file": (
            "data.geojson",
            b'{"type": "FeatureCollection", "features": []}',
            "application/json",
        )
    }
    response = client.post("/api/files/", files=files)
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_oversized_file(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming upload enforces MAX_UPLOAD_MB and aborts with 413 FILE_TOO_LARGE."""
    # Temporarily set max upload to 1 MB for testing
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    large_content = b"0" * (1024 * 1024 + 100)  # > 1 MB

    files = {"file": ("big.kml", large_content, "application/vnd.google-earth.kml+xml")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 413
    data = response.json()
    assert data["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_corrupt_zip(client: TestClient) -> None:
    """Corrupted zip archive returns 422 INVALID_ARCHIVE."""
    files = {"file": ("corrupt.zip", b"PK\x03\x04not-a-valid-zip-content", "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "INVALID_ARCHIVE"


def test_upload_zip_slip_rejected(client: TestClient) -> None:
    """Zip slip attempt (e.g. ../../evil.txt) is detected and returns 422 INVALID_ARCHIVE."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../evil.txt", "evil payload")
    zip_buffer.seek(0)

    files = {"file": ("slip.zip", zip_buffer.getvalue(), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "INVALID_ARCHIVE"
    assert "Zip slip" in data["error"]["message"]


def test_upload_zip_bomb_file_count_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zip containing more files than MAX_ZIP_FILES returns 422 INVALID_ARCHIVE."""
    monkeypatch.setattr(settings, "MAX_ZIP_FILES", 5)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for i in range(6):
            zf.writestr(f"file_{i}.txt", f"content_{i}")
    zip_buffer.seek(0)

    files = {"file": ("bomb.zip", zip_buffer.getvalue(), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "INVALID_ARCHIVE"
    assert "limit" in data["error"]["message"].lower()


def test_upload_zip_missing_shp(client: TestClient) -> None:
    """Zip archive containing no .shp file returns 422 MISSING_SHAPEFILE_COMPONENT."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("readme.txt", "just a text file")
    zip_buffer.seek(0)

    files = {"file": ("no_shp.zip", zip_buffer.getvalue(), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "MISSING_SHAPEFILE_COMPONENT"


def test_upload_zip_missing_shx_or_dbf(client: TestClient) -> None:
    """Zip archive with .shp but missing .shx / .dbf returns 422 MISSING_SHAPEFILE_COMPONENT."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("layer.shp", b"dummy shp")
        zf.writestr(
            "layer.prj",
            'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',
        )
    zip_buffer.seek(0)

    files = {"file": ("missing_shx.zip", zip_buffer.getvalue(), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "MISSING_SHAPEFILE_COMPONENT"


def test_upload_zip_missing_prj(client: TestClient) -> None:
    """Zip archive with .shp, .shx, .dbf but missing .prj returns 422 MISSING_CRS."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("layer.shp", b"dummy shp")
        zf.writestr("layer.shx", b"dummy shx")
        zf.writestr("layer.dbf", b"dummy dbf")
    zip_buffer.seek(0)

    files = {"file": ("missing_prj.zip", zip_buffer.getvalue(), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "MISSING_CRS"
