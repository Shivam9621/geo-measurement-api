from shapely.geometry import Point

from app.services.crs import select_measurement_crs


def test_utm_zone_selection_bengaluru() -> None:
    """Bengaluru (~77.6°E, 12.97°N) selects UTM zone 43N -> EPSG:32643."""
    bengaluru_pt = Point(77.59, 12.97)
    crs_code, note = select_measurement_crs(bengaluru_pt)
    assert crs_code == "EPSG:32643"
    assert note is None


def test_utm_zone_selection_sydney() -> None:
    """Sydney (~151.2°E, -33.86°S) selects UTM zone 56S -> EPSG:32756."""
    sydney_pt = Point(151.2, -33.86)
    crs_code, note = select_measurement_crs(sydney_pt)
    assert crs_code.startswith("EPSG:327")
    assert crs_code == "EPSG:32756"
    assert note is None


def test_polar_selection_north() -> None:
    """Latitude > 84°N selects Polar Stereographic North (EPSG:3413)."""
    north_pole_pt = Point(10.0, 85.5)
    crs_code, note = select_measurement_crs(north_pole_pt)
    assert crs_code == "EPSG:3413"
    assert note is not None
    assert "Polar region" in note


def test_polar_selection_south() -> None:
    """Latitude < -80°S selects Antarctic Polar Stereographic (EPSG:3031)."""
    south_pole_pt = Point(10.0, -82.0)
    crs_code, note = select_measurement_crs(south_pole_pt)
    assert crs_code == "EPSG:3031"
    assert note is not None
    assert "Antarctic" in note
