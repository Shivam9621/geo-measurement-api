from fastapi.testclient import TestClient


def test_get_measurements_and_filtering(client: TestClient) -> None:
    """GET /api/files/{id}/measurements/ returns correct values, handles pagination, filtering, and include_geometry."""
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
        "file": (
            "measure_test.kml",
            kml_content.encode("utf-8"),
            "application/vnd.google-earth.kml+xml",
        )
    }
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    # 1. Fetch all measurements
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    data = meas_resp.json()
    assert data["file_id"] == file_id
    assert data["total"] == 3
    assert len(data["features"]) == 3

    # Feature 0: Polygon
    poly_feat = data["features"][0]
    assert poly_feat["geometry_type"] == "Polygon"
    assert poly_feat["geometry"] is not None
    assert poly_feat["measurement"]["status"] == "OK"
    assert poly_feat["measurement"]["type"] == "area"
    assert poly_feat["measurement"]["unit"] == "m2"
    assert poly_feat["measurement"]["value"] > 0
    assert "hectares" in poly_feat["measurement"]["also"]
    assert "sq_km" in poly_feat["measurement"]["also"]
    assert poly_feat["measurement"]["geodesic_value"] > 0

    # Feature 1: LineString
    line_feat = data["features"][1]
    assert line_feat["geometry_type"] == "LineString"
    assert line_feat["measurement"]["status"] == "OK"
    assert line_feat["measurement"]["type"] == "length"
    assert line_feat["measurement"]["unit"] == "m"
    assert "km" in line_feat["measurement"]["also"]

    # Feature 2: Point
    pt_feat = data["features"][2]
    assert pt_feat["geometry_type"] == "Point"
    assert pt_feat["measurement"]["status"] == "NOT_APPLICABLE"
    assert pt_feat["measurement"]["value"] is None

    # 2. Test pagination
    paged_resp = client.get(f"/api/files/{file_id}/measurements/?limit=1&offset=1")
    assert paged_resp.status_code == 200
    paged_data = paged_resp.json()
    assert paged_data["total"] == 3
    assert len(paged_data["features"]) == 1
    assert paged_data["features"][0]["index"] == 1

    # 3. Test geometry_type filter
    filter_resp = client.get(f"/api/files/{file_id}/measurements/?geometry_type=Polygon")
    assert filter_resp.status_code == 200
    filter_data = filter_resp.json()
    assert filter_data["total"] == 1
    assert filter_data["features"][0]["geometry_type"] == "Polygon"

    # 4. Test include_geometry=false
    no_geom_resp = client.get(f"/api/files/{file_id}/measurements/?include_geometry=false")
    assert no_geom_resp.status_code == 200
    no_geom_data = no_geom_resp.json()
    for f in no_geom_data["features"]:
        assert f["geometry"] is None


def test_measurements_unknown_file_returns_404(client: TestClient) -> None:
    """GET /api/files/{unknown_id}/measurements/ returns 404 FILE_NOT_FOUND."""
    resp = client.get("/api/files/does_not_exist/measurements/")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "FILE_NOT_FOUND"


def test_measurements_failed_file_returns_409(client: TestClient) -> None:
    """GET /api/files/{id}/measurements/ on a failed upload returns 409 FILE_PROCESSING_FAILED."""
    empty_kml = """<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>"""
    files = {
        "file": ("empty.kml", empty_kml.encode("utf-8"), "application/vnd.google-earth.kml+xml")
    }
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 422
    failed_id = upload_resp.json()["error"]["id"]

    meas_resp = client.get(f"/api/files/{failed_id}/measurements/")
    assert meas_resp.status_code == 409
    assert meas_resp.json()["error"]["code"] == "FILE_PROCESSING_FAILED"
