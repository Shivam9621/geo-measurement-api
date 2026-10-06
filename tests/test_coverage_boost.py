from pathlib import Path

import pytest
from shapely.geometry import LinearRing, MultiLineString, Point

from app.core.errors import InvalidGeospatialFileError, MissingCrsError
from app.services.crs import reproject_geometry, reproject_to_wgs84
from app.services.measurement import compute_geodesic_measurement, measure_feature
from app.services.reader import read_geospatial_file, read_shapefile_crs


def test_reproject_crs_branches() -> None:
    """Test reproject_to_wgs84 and reproject_geometry branches."""
    pt = Point(780000, 1435000)
    # Reproject from UTM 43N to 4326
    pt_wgs = reproject_to_wgs84(pt, "EPSG:32643")
    assert pt_wgs.geom_type == "Point"
    assert 70.0 < pt_wgs.x < 80.0

    # Same CRS branch
    pt_same = reproject_geometry(pt, "EPSG:32643", "EPSG:32643")
    assert pt_same.equals(pt)

    # Empty source CRS branch
    pt_empty_src = reproject_to_wgs84(pt, "")
    assert pt_empty_src.equals(pt)

    # Invalid CRS raises InvalidGeospatialFileError
    with pytest.raises(InvalidGeospatialFileError):
        reproject_to_wgs84(pt, "INVALID_CRS_NOT_REAL")


def test_measure_multilinestring_and_linearring() -> None:
    """Measure MultiLineString and LinearRing geometries."""
    # MultiLineString
    mls = MultiLineString(
        [
            [(77.59, 12.97), (77.60, 12.97)],
            [(77.61, 12.98), (77.62, 12.98)],
        ]
    )
    res_mls = measure_feature(mls, "EPSG:4326")
    assert res_mls.status == "OK"
    assert res_mls.type == "length"
    assert res_mls.value is not None and res_mls.value > 0
    assert res_mls.geodesic_value is not None and res_mls.geodesic_value > 0

    # LinearRing
    ring = LinearRing([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.97)])
    res_ring = measure_feature(ring, "EPSG:4326")
    assert res_ring.status == "OK"
    assert res_ring.type == "length"
    assert res_ring.value is not None and res_ring.value > 0


def test_compute_geodesic_edge_cases() -> None:
    """Check compute_geodesic_measurement with unknown types."""
    assert compute_geodesic_measurement(Point(0, 0), "UnknownType") is None


def test_read_shapefile_crs_missing_or_empty_prj(tmp_path: Path) -> None:
    """read_shapefile_crs raises MissingCrsError when .prj is missing or empty."""
    shp = tmp_path / "dummy.shp"
    shp.touch()
    with pytest.raises(MissingCrsError):
        read_shapefile_crs(shp)

    prj = tmp_path / "dummy.prj"
    prj.write_text("")
    with pytest.raises(MissingCrsError):
        read_shapefile_crs(shp)


def test_read_unsupported_geospatial_file(tmp_path: Path) -> None:
    """read_geospatial_file raises InvalidGeospatialFileError for unsupported types."""
    dummy = tmp_path / "test.csv"
    dummy.touch()
    with pytest.raises(InvalidGeospatialFileError):
        read_geospatial_file(dummy, "csv")
