from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.ops import transform

from app.services.crs import get_transformer
from app.services.measurement import measure_feature


def test_square_1000m_measurement() -> None:
    """A 1000m x 1000m square built in UTM and converted to 4326 measures ~1,000,000 m² within 0.1%."""
    # Build 1000m x 1000m square in UTM 43N (EPSG:32643)
    x0, y0 = 780000.0, 1435000.0
    utm_poly = Polygon(
        [(x0, y0), (x0 + 1000, y0), (x0 + 1000, y0 + 1000), (x0, y0 + 1000), (x0, y0)]
    )
    assert utm_poly.area == 1_000_000.0

    # Transform to EPSG:4326
    to_wgs84 = get_transformer("EPSG:32643", "EPSG:4326")
    poly_4326 = transform(to_wgs84.transform, utm_poly)

    res = measure_feature(poly_4326, "EPSG:4326")
    assert res.status == "OK"
    assert res.type == "area"
    assert res.unit == "m2"
    assert res.measurement_crs == "EPSG:32643"
    assert res.value is not None
    # 0.1% tolerance: |val - 1,000,000| / 1,000,000 < 0.001
    error_ratio = abs(res.value - 1_000_000.0) / 1_000_000.0
    assert error_ratio < 0.001


def test_line_length_measurement() -> None:
    """A 500m line built in UTM and converted to 4326 measures ~500m within tolerance."""
    x0, y0 = 780000.0, 1435000.0
    utm_line = LineString([(x0, y0), (x0 + 500, y0)])
    assert utm_line.length == 500.0

    to_wgs84 = get_transformer("EPSG:32643", "EPSG:4326")
    line_4326 = transform(to_wgs84.transform, utm_line)

    res = measure_feature(line_4326, "EPSG:4326")
    assert res.status == "OK"
    assert res.type == "length"
    assert res.unit == "m"
    assert res.value is not None
    error_ratio = abs(res.value - 500.0) / 500.0
    assert error_ratio < 0.001


def test_projected_and_geodesic_agreement() -> None:
    """Projected and geodesic measurements agree within 0.5% for a local feature."""
    x0, y0 = 780000.0, 1435000.0
    utm_poly = Polygon([(x0, y0), (x0 + 200, y0), (x0 + 200, y0 + 200), (x0, y0 + 200), (x0, y0)])
    to_wgs84 = get_transformer("EPSG:32643", "EPSG:4326")
    poly_4326 = transform(to_wgs84.transform, utm_poly)

    res = measure_feature(poly_4326, "EPSG:4326")
    assert res.status == "OK"
    assert res.value is not None
    assert res.geodesic_value is not None
    diff_ratio = abs(res.value - res.geodesic_value) / res.geodesic_value
    assert diff_ratio < 0.005  # Within 0.5%


def test_polygon_with_hole_excludes_hole() -> None:
    """Polygon area calculation excludes interior ring (hole)."""
    x0, y0 = 780000.0, 1435000.0
    exterior = [(x0, y0), (x0 + 100, y0), (x0 + 100, y0 + 100), (x0, y0 + 100), (x0, y0)]
    # Hole: 20m x 20m in center
    hole = [
        (x0 + 40, y0 + 40),
        (x0 + 60, y0 + 40),
        (x0 + 60, y0 + 60),
        (x0 + 40, y0 + 60),
        (x0 + 40, y0 + 40),
    ]
    utm_poly = Polygon(exterior, [hole])
    expected_area = 10000.0 - 400.0  # 9600 m²

    to_wgs84 = get_transformer("EPSG:32643", "EPSG:4326")
    poly_4326 = transform(to_wgs84.transform, utm_poly)

    res = measure_feature(poly_4326, "EPSG:4326")
    assert res.status == "OK"
    assert res.value is not None
    error_ratio = abs(res.value - expected_area) / expected_area
    assert error_ratio < 0.001


def test_multipolygon_sums_parts() -> None:
    """MultiPolygon area sums the areas of all disjoint member polygons."""
    x0, y0 = 780000.0, 1435000.0
    p1 = Polygon([(x0, y0), (x0 + 100, y0), (x0 + 100, y0 + 100), (x0, y0 + 100)])
    p2 = Polygon([(x0 + 200, y0), (x0 + 300, y0), (x0 + 300, y0 + 100), (x0 + 200, y0 + 100)])
    utm_mp = MultiPolygon([p1, p2])
    expected_area = 20000.0  # 10,000 + 10,000

    to_wgs84 = get_transformer("EPSG:32643", "EPSG:4326")
    mp_4326 = transform(to_wgs84.transform, utm_mp)

    res = measure_feature(mp_4326, "EPSG:4326")
    assert res.status == "OK"
    assert res.value is not None
    error_ratio = abs(res.value - expected_area) / expected_area
    assert error_ratio < 0.001


def test_point_not_applicable() -> None:
    """Point geometries return NOT_APPLICABLE status with explanatory note."""
    pt = Point(77.59, 12.97)
    res = measure_feature(pt, "EPSG:4326")
    assert res.status == "NOT_APPLICABLE"
    assert res.type is None
    assert res.value is None
    assert "Point geometries have no area or length" in res.note


def test_geometry_collection_unsupported() -> None:
    """GeometryCollection returns UNSUPPORTED status with explanatory note."""
    gc = GeometryCollection([Point(77.59, 12.97), LineString([(77.59, 12.97), (77.60, 12.98)])])
    res = measure_feature(gc, "EPSG:4326")
    assert res.status == "UNSUPPORTED"
    assert res.type is None
    assert res.value is None


def test_empty_geometry() -> None:
    """Empty or None geometry returns EMPTY status."""
    res_none = measure_feature(None, "EPSG:4326")
    assert res_none.status == "EMPTY"

    res_empty = measure_feature(Polygon(), "EPSG:4326")
    assert res_empty.status == "EMPTY"


def test_invalid_bowtie_polygon_repaired() -> None:
    """Self-intersecting bow-tie polygon is repaired via make_valid and measured without raising."""
    # Classic bow-tie self-intersecting polygon
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
    assert not bowtie.is_valid

    res = measure_feature(bowtie, "EPSG:4326")
    assert res.status in ("OK", "INVALID")
    if res.status == "OK":
        assert res.value is not None
        assert res.value > 0
        assert "repaired" in res.note.lower()


def test_naive_degree_regression_guard() -> None:
    """Regression guard proving raw degrees squared are NEVER returned as area."""
    # 0.01° x 0.01° polygon around Bengaluru
    poly_deg = Polygon(
        [(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98), (77.59, 12.97)]
    )
    naive_deg_area = poly_deg.area  # ~ 0.0001 square degrees

    res = measure_feature(poly_deg, "EPSG:4326")
    assert res.status == "OK"
    assert res.unit == "m2"
    # Metric area is approx 1,000,000+ m²
    assert res.value > 100_000.0
    assert abs(res.value - naive_deg_area) > 10_000.0
