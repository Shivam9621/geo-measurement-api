from functools import lru_cache
import pyproj
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.core.errors import InvalidGeospatialFileError


@lru_cache(maxsize=128)
def get_transformer(src_crs_str: str, dst_crs_str: str) -> pyproj.Transformer:
    """
    Get or create a cached pyproj Transformer between two CRS definitions.
    Always uses always_xy=True to guarantee (longitude, latitude) / (x, y) ordering.
    """
    src = pyproj.CRS.from_user_input(src_crs_str)
    dst = pyproj.CRS.from_user_input(dst_crs_str)
    return pyproj.Transformer.from_crs(src, dst, always_xy=True)


def reproject_to_wgs84(geom: BaseGeometry, src_crs_str: str) -> BaseGeometry:
    """Reproject a geometry from src_crs into EPSG:4326 (WGS 84)."""
    if not src_crs_str:
        return geom

    try:
        src_crs = pyproj.CRS.from_user_input(src_crs_str)
        if src_crs.to_epsg() == 4326:
            return geom
    except Exception:
        pass

    try:
        transformer = get_transformer(src_crs_str, "EPSG:4326")
        return transform(transformer.transform, geom)
    except Exception as e:
        raise InvalidGeospatialFileError(f"Failed to reproject geometry to EPSG:4326: {e}") from e


def select_measurement_crs(geom_4326: BaseGeometry) -> tuple[str, str | None]:
    """
    Determine the optimal metric projected CRS (UTM or Polar Stereographic)
    based on the geometry's centroid in EPSG:4326.

    Returns:
        tuple[epsg_string, optional_note]
    """
    centroid = geom_4326.centroid
    lon, lat = centroid.x, centroid.y

    # Polar cases: north of 84°N or south of 80°S
    if lat > 84.0:
        return "EPSG:3413", "Polar region (>84°N): using WGS 84 / NSIDC Sea Ice Polar Stereographic North (EPSG:3413)."
    elif lat < -80.0:
        return "EPSG:3031", "Polar region (<-80°S): using Antarctic Polar Stereographic (EPSG:3031)."

    # Standard UTM Zone calculation
    # Zone 1 to 60, each 6 degrees wide
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(60, zone))

    if lat >= 0.0:
        epsg_code = 32600 + zone
    else:
        epsg_code = 32700 + zone

    return f"EPSG:{epsg_code}", None


def reproject_geometry(geom: BaseGeometry, src_crs_str: str, dst_crs_str: str) -> BaseGeometry:
    """Reproject geometry from source CRS to destination projected CRS."""
    if src_crs_str == dst_crs_str:
        return geom
    transformer = get_transformer(src_crs_str, dst_crs_str)
    return transform(transformer.transform, geom)
