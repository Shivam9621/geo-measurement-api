import datetime
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyproj
import shapefile
import shapely
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    shape,
)

from app.core.errors import (
    InvalidGeospatialFileError,
    MissingCrsError,
    NoFeaturesError,
)


@dataclass
class ParsedFeature:
    """Normalized feature representation extracted from a geospatial file."""

    index: int
    geometry: shapely.Geometry | None
    properties: dict[str, Any]
    crs: str


def make_json_safe(value: Any) -> Any:
    """Recursively convert values into JSON-serializable types."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (int, bool, str)):
        return value
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("latin-1", errors="replace")
    if hasattr(value, "item"):  # numpy scalars
        try:
            return make_json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(v) for v in value]
    return str(value)


def read_shapefile_crs(shp_path: Path) -> tuple[pyproj.CRS, str]:
    """Read and parse CRS from companion .prj file."""
    parent = shp_path.parent
    stem = shp_path.stem
    prj_files = [
        f for f in parent.iterdir() if f.is_file() and f.name.lower() == f"{stem}.prj".lower()
    ]

    if not prj_files:
        raise MissingCrsError(
            f"Shapefile '{shp_path.name}' is missing companion .prj projection file."
        )

    prj_text = prj_files[0].read_text(encoding="utf-8", errors="replace").strip()
    if not prj_text:
        raise MissingCrsError(f"Projection file '{prj_files[0].name}' is empty.")

    try:
        crs_obj = pyproj.CRS.from_user_input(prj_text)
    except Exception as e:
        raise InvalidGeospatialFileError(f"Unable to parse CRS from .prj file: {e}") from e

    epsg = crs_obj.to_epsg()
    crs_str = f"EPSG:{epsg}" if epsg else (crs_obj.to_string() or crs_obj.name or "UNKNOWN")
    return crs_obj, crs_str


def read_shapefile(shp_path: Path) -> tuple[list[ParsedFeature], str]:
    """Extract features from ESRI Shapefile using pure-python shapefile reader."""
    _, crs_str = read_shapefile_crs(shp_path)

    try:
        sf = shapefile.Reader(str(shp_path))
    except Exception as e:
        raise InvalidGeospatialFileError(f"Failed to read Shapefile: {e}") from e

    features: list[ParsedFeature] = []
    with sf:
        records = sf.iterShapeRecords()
        for idx, item in enumerate(records):
            raw_props = item.record.as_dict()
            safe_props = make_json_safe(raw_props)

            geom: shapely.Geometry | None = None
            if item.shape and item.shape.shapeType != shapefile.NULL and len(item.shape.points) > 0:
                try:
                    raw_geom = shape(item.shape.__geo_interface__)
                    geom = shapely.force_2d(raw_geom)
                except Exception:
                    geom = None

            features.append(
                ParsedFeature(
                    index=idx,
                    geometry=geom,
                    properties=safe_props,
                    crs=crs_str,
                )
            )

    if not features:
        raise NoFeaturesError("Shapefile contains no features.")

    return features, crs_str


# Helper functions for robust KML parsing
def _parse_coordinates(coord_text: str) -> list[tuple[float, ...]]:
    """Parse coordinate string from KML coordinates tag."""
    coords: list[tuple[float, ...]] = []
    for token in coord_text.strip().split():
        parts = [p.strip() for p in token.split(",") if p.strip()]
        if len(parts) >= 2:
            try:
                coords.append(tuple(float(p) for p in parts))
            except ValueError:
                continue
    return coords


def _parse_kml_geometry(elem: ET.Element) -> shapely.Geometry | None:
    """Extract shapely geometry from a KML geometry element."""
    tag = elem.tag.split("}")[-1]

    if tag == "Point":
        coord_elem = elem.find(".//{*}coordinates")
        if coord_elem is not None and coord_elem.text:
            coords = _parse_coordinates(coord_elem.text)
            if coords:
                return Point(coords[0][:2])
        return None

    elif tag in ("LineString", "LinearRing"):
        coord_elem = elem.find(".//{*}coordinates")
        if coord_elem is not None and coord_elem.text:
            coords = _parse_coordinates(coord_elem.text)
            if len(coords) >= 2:
                pts = [c[:2] for c in coords]
                return LineString(pts)
        return None

    elif tag == "Polygon":
        outer_elem = elem.find(".//{*}outerBoundaryIs//{*}coordinates")
        if outer_elem is None or not outer_elem.text:
            return None
        outer_coords = [c[:2] for c in _parse_coordinates(outer_elem.text)]
        if len(outer_coords) < 3:
            return None

        holes: list[list[tuple[float, float]]] = []
        for inner_elem in elem.findall(".//{*}innerBoundaryIs//{*}coordinates"):
            if inner_elem.text:
                inner_coords = [c[:2] for c in _parse_coordinates(inner_elem.text)]
                if len(inner_coords) >= 3:
                    holes.append(inner_coords)

        return Polygon(outer_coords, holes)

    elif tag == "MultiGeometry":
        sub_geoms: list[shapely.Geometry] = []
        for child in elem:
            child_geom = _parse_kml_geometry(child)
            if child_geom is not None and not child_geom.is_empty:
                sub_geoms.append(child_geom)

        if not sub_geoms:
            return None

        # Determine if homogenous or heterogeneous collection
        if all(isinstance(g, Polygon) for g in sub_geoms):
            return MultiPolygon(sub_geoms)
        elif all(isinstance(g, LineString) for g in sub_geoms):
            return MultiLineString(sub_geoms)
        elif all(isinstance(g, Point) for g in sub_geoms):
            return MultiPoint(sub_geoms)
        else:
            return GeometryCollection(sub_geoms)

    return None


def read_kml(kml_path: Path) -> tuple[list[ParsedFeature], str]:
    """
    Parse KML file, extracting all Placemarks across all folders and documents.
    Normalizes coordinates to 2D and tracks layers. KML is always EPSG:4326.
    """
    crs_str = "EPSG:4326"

    try:
        content = kml_path.read_bytes()
        root = ET.fromstring(content)
    except Exception as e:
        raise InvalidGeospatialFileError(f"Failed to parse KML file: {e}") from e

    # Traverse DOM and extract Placemarks
    raw_features: list[dict[str, Any]] = []
    layer_names_seen: set[str] = set()

    def traverse(elem: ET.Element, current_folder: str | None = None) -> None:
        tag = elem.tag.split("}")[-1]
        folder = current_folder

        if tag == "Folder":
            name_elem = elem.find("{*}name")
            if name_elem is not None and name_elem.text:
                folder = name_elem.text.strip()
                layer_names_seen.add(folder)

        if tag == "Placemark":
            props: dict[str, Any] = {}
            if folder:
                props["_layer"] = folder

            name_elem = elem.find("{*}name")
            if name_elem is not None and name_elem.text:
                props["name"] = name_elem.text.strip()

            desc_elem = elem.find("{*}description")
            if desc_elem is not None and desc_elem.text:
                props["description"] = desc_elem.text.strip()

            # Parse SimpleData / Data
            for data in elem.findall(".//{*}Data"):
                data_name = data.get("name")
                val_elem = data.find("{*}value")
                if data_name and val_elem is not None and val_elem.text:
                    props[data_name] = val_elem.text.strip()

            for simple_data in elem.findall(".//{*}SimpleData"):
                s_name = simple_data.get("name")
                if s_name and simple_data.text:
                    props[s_name] = simple_data.text.strip()

            # Find geometry tag in placemark
            geom: shapely.Geometry | None = None
            for child in elem:
                child_tag = child.tag.split("}")[-1]
                if child_tag in ("Point", "LineString", "LinearRing", "Polygon", "MultiGeometry"):
                    raw_g = _parse_kml_geometry(child)
                    if raw_g is not None:
                        geom = shapely.force_2d(raw_g)
                    break

            raw_features.append({"geom": geom, "props": props})
            return

        for child in elem:
            traverse(child, folder)

    traverse(root)

    if not raw_features:
        raise NoFeaturesError("KML file contains no features.")

    has_multiple_layers = len(layer_names_seen) > 1
    features: list[ParsedFeature] = []

    for idx, item in enumerate(raw_features):
        props = item["props"]
        layer_val = props.pop("_layer", None)
        if has_multiple_layers and layer_val:
            props["layer"] = layer_val

        safe_props = make_json_safe(props)
        features.append(
            ParsedFeature(
                index=idx,
                geometry=item["geom"],
                properties=safe_props,
                crs=crs_str,
            )
        )

    return features, crs_str


def read_geospatial_file(file_path: Path, file_type: str) -> tuple[list[ParsedFeature], str]:
    """
    Unified entry point for reading supported geospatial files.

    Returns:
        tuple[features, crs_string]
    """
    if file_type == "shapefile":
        return read_shapefile(file_path)
    elif file_type == "kml":
        return read_kml(file_path)
    else:
        raise InvalidGeospatialFileError(f"Unsupported file type: {file_type}")
