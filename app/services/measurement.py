from dataclasses import dataclass

import pyproj
import shapely
from shapely.geometry.base import BaseGeometry

from app.services.crs import (
    reproject_geometry,
    reproject_to_wgs84,
    select_measurement_crs,
)

geod_wgs84 = pyproj.Geod(ellps="WGS84")


@dataclass
class MeasurementResult:
    """Standardized result of geospatial measurement calculations."""

    status: str  # OK, NOT_APPLICABLE, UNSUPPORTED, INVALID, EMPTY, ERROR
    type: str | None = None  # area, length, or None
    value: float | None = None
    unit: str | None = None  # m2, m, or None
    also: dict[str, float] | None = None
    geodesic_value: float | None = None
    measurement_crs: str | None = None
    note: str | None = None


def compute_geodesic_measurement(geom_4326: BaseGeometry, geom_type: str) -> float | None:
    """Compute ellipsoidal geodesic area (m²) or length (m) on WGS84."""
    try:
        if geom_type == "Polygon":
            area, _ = geod_wgs84.geometry_area_perimeter(geom_4326)
            return abs(float(area))
        elif geom_type == "MultiPolygon":
            total_area = sum(
                abs(float(geod_wgs84.geometry_area_perimeter(poly)[0])) for poly in geom_4326.geoms
            )
            return total_area
        elif geom_type in ("LineString", "LinearRing"):
            return float(geod_wgs84.geometry_length(geom_4326))
        elif geom_type == "MultiLineString":
            total_length = sum(float(geod_wgs84.geometry_length(ls)) for ls in geom_4326.geoms)
            return total_length
    except Exception:
        return None
    return None


def measure_feature(geom: BaseGeometry | None, source_crs: str) -> MeasurementResult:
    """
    Measure an individual feature with automatic projected CRS selection,
    handling holes, multi-part shapes, invalid geometry repairs, and geodesic checks.
    """
    if geom is None or geom.is_empty:
        return MeasurementResult(status="EMPTY")

    geom_type = geom.geom_type

    # Non-measurable types
    if geom_type in ("Point", "MultiPoint"):
        return MeasurementResult(
            status="NOT_APPLICABLE",
            note="Point geometries have no area or length.",
        )

    if geom_type == "GeometryCollection":
        return MeasurementResult(
            status="UNSUPPORTED",
            note="GeometryCollection geometries are unsupported.",
        )

    repair_note: str | None = None

    # Handle invalid polygons via shapely.make_valid
    if geom_type in ("Polygon", "MultiPolygon") and not geom.is_valid:
        try:
            repaired = shapely.make_valid(geom)
            if repaired is None or repaired.is_empty:
                return MeasurementResult(
                    status="INVALID",
                    note="Geometry was invalid and could not be repaired.",
                )
            geom = repaired
            geom_type = geom.geom_type
            repair_note = "Geometry was invalid and was repaired before measuring."
        except Exception as e:
            return MeasurementResult(
                status="INVALID",
                note=f"Geometry validation/repair failed: {e}",
            )

    try:
        # Reproject to WGS84 to locate centroid and calculate geodesic truth
        geom_4326 = reproject_to_wgs84(geom, source_crs)
        measurement_crs, polar_note = select_measurement_crs(geom_4326)

        # Reproject to metric projected coordinate system
        projected_geom = reproject_geometry(geom_4326, "EPSG:4326", measurement_crs)

        notes: list[str] = []
        if repair_note:
            notes.append(repair_note)
        if polar_note:
            notes.append(polar_note)
        final_note = "; ".join(notes) if notes else None

        # Calculate projected measurements
        if geom_type in ("Polygon", "MultiPolygon"):
            # Area in square meters (excludes interior holes natively)
            raw_val = float(projected_geom.area)
            val = round(raw_val, 2)
            also = {
                "hectares": round(raw_val / 10000.0, 4),
                "sq_km": round(raw_val / 1000000.0, 4),
            }
            geodesic_val = compute_geodesic_measurement(geom_4326, geom_type)
            if geodesic_val is not None:
                geodesic_val = round(geodesic_val, 2)

            return MeasurementResult(
                status="OK",
                type="area",
                value=val,
                unit="m2",
                also=also,
                geodesic_value=geodesic_val,
                measurement_crs=measurement_crs,
                note=final_note,
            )

        elif geom_type in ("LineString", "MultiLineString", "LinearRing"):
            # Length in meters
            raw_val = float(projected_geom.length)
            val = round(raw_val, 2)
            also = {
                "km": round(raw_val / 1000.0, 4),
            }
            geodesic_val = compute_geodesic_measurement(geom_4326, geom_type)
            if geodesic_val is not None:
                geodesic_val = round(geodesic_val, 2)

            return MeasurementResult(
                status="OK",
                type="length",
                value=val,
                unit="m",
                also=also,
                geodesic_value=geodesic_val,
                measurement_crs=measurement_crs,
                note=final_note,
            )

        else:
            return MeasurementResult(
                status="UNSUPPORTED",
                note=f"Unsupported geometry type: {geom_type}",
            )

    except Exception as e:
        return MeasurementResult(
            status="ERROR",
            note=f"Unexpected measurement error: {e}",
        )
