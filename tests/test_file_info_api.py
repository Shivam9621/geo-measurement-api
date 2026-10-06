from fastapi.testclient import TestClient


def test_get_file_info_and_list(client: TestClient) -> None:
    """GET /api/files/{id}/ matches contract and /api/files/ lists uploads."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Point A</name>
      <Point><coordinates>77.59,12.97,0</coordinates></Point>
    </Placemark>
  </Document>
</kml>"""

    files = {"file": ("test.kml", kml_content.encode("utf-8"), "application/vnd.google-earth.kml+xml")}
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    # Test GET /api/files/{id}/
    resp = client.get(f"/api/files/{file_id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == file_id
    assert data["filename"] == "test.kml"
    assert data["file_type"] == "kml"
    assert data["feature_count"] == 1
    assert data["crs"] == "EPSG:4326"
    assert data["status"] == "COMPLETED"
    assert data["created_at"] is not None
    assert data["completed_at"] is not None

    # Test GET /api/files/
    list_resp = client.get("/api/files/")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(f["id"] == file_id for f in list_data["files"])


def test_get_file_unknown_id_404(client: TestClient) -> None:
    """GET /api/files/{unknown_id}/ returns 404 FILE_NOT_FOUND."""
    resp = client.get("/api/files/nonexistent123/")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "FILE_NOT_FOUND"


def test_file_summary_and_deletion(client: TestClient) -> None:
    """GET /api/files/{id}/summary/ computes totals and DELETE removes the file."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Plot A</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.97,0</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""

    files = {"file": ("summary.kml", kml_content.encode("utf-8"), "application/vnd.google-earth.kml+xml")}
    upload_resp = client.post("/api/files/", files=files)
    file_id = upload_resp.json()["id"]

    # Test summary
    summary_resp = client.get(f"/api/files/{file_id}/summary/")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_features"] == 1
    assert summary_data["total_area_m2"] > 0
    assert summary_data["counts_by_geometry_type"]["Polygon"] == 1

    # Test deletion
    del_resp = client.delete(f"/api/files/{file_id}/")
    assert del_resp.status_code == 204

    # Now verify it is gone
    get_after_del = client.get(f"/api/files/{file_id}/")
    assert get_after_del.status_code == 404
