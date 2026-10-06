from datetime import date, datetime
import math
from pathlib import Path
import pyproj
import shapefile
from shapely.geometry import LineString, Point, Polygon

from app.services.reader import make_json_safe, read_geospatial_file


def test_make_json_safe() -> None:
    """Verify make_json_safe handles dates, NaN, Inf, bytes, and nested dicts."""
    raw = {
        "str": "hello",
        "int": 42,
        "float_nan": float("nan"),
        "float_inf": float("inf"),
        "date": date(2026, 10, 6),
        "datetime": datetime(2026, 10, 6, 12, 0, 0),
        "bytes": b"test_utf8",
        "nested": {"val": float("nan")},
        "list": [float("nan"), 10],
    }
    safe = make_json_safe(raw)
    assert safe["str"] == "hello"
    assert safe["int"] == 42
    assert safe["float_nan"] is None
    assert safe["float_inf"] is None
    assert safe["date"] == "2026-10-06"
    assert safe["datetime"] == "2026-10-06T12:00:00"
    assert safe["bytes"] == "test_utf8"
    assert safe["nested"]["val"] is None
    assert safe["list"] == [None, 10]


def test_read_kml_polygon_linestring_point(tmp_path: Path) -> None:
    """KML with Polygon, LineString and Point reads correctly with 3D Z stripped."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Test Polygon</name>
      <description>Polygon Desc</description>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.59,12.97,100 77.60,12.97,100 77.60,12.98,100 77.59,12.97,100
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>Test Line</name>
      <LineString>
        <coordinates>77.59,12.97,50 77.61,12.99,50</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Test Point</name>
      <Point>
        <coordinates>77.60,12.98,25</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""

    kml_file = tmp_path / "test.kml"
    kml_file.write_text(kml_content, encoding="utf-8")

    features, crs_str = read_geospatial_file(kml_file, "kml")
    assert crs_str == "EPSG:4326"
    assert len(features) == 3

    # Check Polygon
    f0 = features[0]
    assert f0.geometry.geom_type == "Polygon"
    assert not f0.geometry.has_z
    assert f0.properties["name"] == "Test Polygon"
    assert f0.properties["description"] == "Polygon Desc"

    # Check LineString
    f1 = features[1]
    assert f1.geometry.geom_type == "LineString"
    assert not f1.geometry.has_z
    assert f1.properties["name"] == "Test Line"

    # Check Point
    f2 = features[2]
    assert f2.geometry.geom_type == "Point"
    assert not f2.geometry.has_z
    assert f2.properties["name"] == "Test Point"


def test_read_kml_multiple_layers(tmp_path: Path) -> None:
    """KML with multiple folders retains 'layer' key in properties."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Parcels</name>
      <Placemark>
        <name>Plot 1</name>
        <Point><coordinates>77.5,12.5</coordinates></Point>
      </Placemark>
    </Folder>
    <Folder>
      <name>Roads</name>
      <Placemark>
        <name>Main St</name>
        <LineString><coordinates>77.5,12.5 77.6,12.6</coordinates></LineString>
      </Placemark>
    </Folder>
  </Document>
</kml>"""

    kml_file = tmp_path / "layers.kml"
    kml_file.write_text(kml_content, encoding="utf-8")

    features, _ = read_geospatial_file(kml_file, "kml")
    assert len(features) == 2
    assert features[0].properties["layer"] == "Parcels"
    assert features[1].properties["layer"] == "Roads"


def test_read_shapefile_epsg_4326(tmp_path: Path) -> None:
    """Shapefile in EPSG:4326 reads all features with properties and CRS."""
    shp_path = tmp_path / "parcels.shp"
    w = shapefile.Writer(str(shp_path))
    w.field("name", "C")
    w.field("area_val", "N", decimal=2)

    poly = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.97)])
    # Shapefile ring orientation
    w.poly([list(poly.exterior.coords)])
    w.record("Plot A", 123.45)
    w.close()

    # Write PRJ
    prj_path = tmp_path / "parcels.prj"
    prj_path.write_text(pyproj.CRS.from_epsg(4326).to_wkt(), encoding="utf-8")

    features, crs_str = read_geospatial_file(shp_path, "shapefile")
    assert crs_str == "EPSG:4326"
    assert len(features) == 1
    assert features[0].properties["name"] == "Plot A"
    assert features[0].properties["area_val"] == 123.45
    assert features[0].geometry.geom_type == "Polygon"


def test_read_shapefile_non_4326(tmp_path: Path) -> None:
    """Shapefile in non-4326 CRS (e.g. EPSG:32643) correctly extracts the CRS."""
    shp_path = tmp_path / "projected.shp"
    w = shapefile.Writer(str(shp_path))
    w.field("name", "C")

    # UTM coordinates
    w.line([[(781000, 1435000), (782000, 1436000)]])
    w.record("Route 66")
    w.close()

    prj_path = tmp_path / "projected.prj"
    prj_path.write_text(pyproj.CRS.from_epsg(32643).to_wkt(), encoding="utf-8")

    features, crs_str = read_geospatial_file(shp_path, "shapefile")
    assert "32643" in crs_str
    assert len(features) == 1
    assert features[0].properties["name"] == "Route 66"
    assert features[0].geometry.geom_type == "LineString"
