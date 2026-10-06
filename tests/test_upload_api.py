import io
import zipfile
from pathlib import Path

import pyproj
import shapefile
from fastapi.testclient import TestClient
from shapely.geometry import Polygon


def test_upload_valid_kml(client: TestClient) -> None:
    """Upload valid KML returns 201 with COMPLETED status and correct feature_count."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Plot A</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.97,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Road 1</name>
      <LineString>
        <coordinates>77.59,12.97,0 77.61,12.99,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Gate</name>
      <Point>
        <coordinates>77.60,12.98,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

    files = {
        "file": ("survey.kml", kml_content.encode("utf-8"), "application/vnd.google-earth.kml+xml")
    }
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["filename"] == "survey.kml"
    assert data["feature_count"] == 3
    assert data["crs"] == "EPSG:4326"
    assert data["status"] == "COMPLETED"


def test_upload_valid_zipped_shapefile(client: TestClient, tmp_path: Path) -> None:
    """Upload valid zipped Shapefile returns 201 with COMPLETED status."""
    shp_base = tmp_path / "valid_shp"
    w = shapefile.Writer(str(shp_base))
    w.field("name", "C")
    poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.97)])
    w.poly([list(poly.exterior.coords)])
    w.record("Plot 1")
    w.close()

    # Companion PRJ
    prj_file = tmp_path / "valid_shp.prj"
    prj_file.write_text(pyproj.CRS.from_epsg(4326).to_wkt(), encoding="utf-8")

    # Zip the shapefile set
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for ext in (".shp", ".shx", ".dbf", ".prj"):
            fpath = tmp_path / f"valid_shp{ext}"
            zf.write(fpath, arcname=f"valid_shp{ext}")
    zip_buffer.seek(0)

    files = {"file": ("parcels.zip", zip_buffer.getvalue(), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "parcels.zip"
    assert data["feature_count"] == 1
    assert data["status"] == "COMPLETED"


def test_upload_mix_including_geometry_collection(client: TestClient) -> None:
    """File with a mix including GeometryCollection completes; that feature is UNSUPPORTED, others measured."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Normal Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.97,0</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Mixed Collection</name>
      <MultiGeometry>
        <Point><coordinates>77.59,12.97,0</coordinates></Point>
        <LineString><coordinates>77.59,12.97,0 77.60,12.98,0</coordinates></LineString>
      </MultiGeometry>
    </Placemark>
  </Document>
</kml>"""

    files = {
        "file": ("mixed.kml", kml_content.encode("utf-8"), "application/vnd.google-earth.kml+xml")
    }
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    file_id = response.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    feats = meas_resp.json()["features"]
    assert len(feats) == 2
    assert feats[0]["measurement"]["status"] == "OK"
    assert feats[1]["measurement"]["status"] == "UNSUPPORTED"


def test_upload_empty_features_returns_422_and_persists_failed(client: TestClient) -> None:
    """Empty geospatial file returns 422 NO_FEATURES and persists status=FAILED in DB."""
    empty_kml = """<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>"""
    files = {
        "file": ("empty.kml", empty_kml.encode("utf-8"), "application/vnd.google-earth.kml+xml")
    }
    response = client.post("/api/files/", files=files)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "NO_FEATURES"
    assert "id" in data["error"]
    failed_id = data["error"]["id"]

    # Verify that the file can be inspected via GET /api/files/{id}/
    info_resp = client.get(f"/api/files/{failed_id}/")
    assert info_resp.status_code == 200
    info_data = info_resp.json()
    assert info_data["status"] == "FAILED"
    assert info_data["error_message"] is not None
