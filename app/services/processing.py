import logging
from datetime import UTC, datetime
from pathlib import Path

import shapely.geometry
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Feature, UploadedFile
from app.services.measurement import MeasurementResult, measure_feature
from app.services.reader import read_geospatial_file
from app.services.storage import cleanup_path, extract_and_locate_shapefile

logger = logging.getLogger("geo-measurement-api.processing")
BATCH_SIZE = 500


def process_file(
    upload_record: UploadedFile,
    file_path: Path,
    file_type: str,
    db: Session,
) -> UploadedFile:
    """
    Synchronous processing orchestrator:
    1. Extracts shapefile archive or targets KML directly.
    2. Reads and parses all features and detects source CRS.
    3. Calculates metric measurements and geodesic cross-checks.
    4. Persists features in batches.
    5. Finalizes status and cleans up temporary extraction artifacts.
    """
    extract_dir: Path | None = None

    try:
        if file_type == "shapefile":
            extract_dir = file_path.parent / "extracted"
            target_path = extract_and_locate_shapefile(file_path, extract_dir)
        else:
            target_path = file_path

        # Parse normalized features
        parsed_features, crs_str = read_geospatial_file(target_path, file_type)

        feature_db_records: list[Feature] = []
        for feat in parsed_features:
            # Per-feature error isolation
            try:
                res = measure_feature(feat.geometry, crs_str)
            except Exception as e:
                logger.error(f"Error measuring feature index {feat.index}: {e}")
                res = MeasurementResult(status="ERROR", note=f"Feature calculation error: {e}")

            geom_geojson = (
                shapely.geometry.mapping(feat.geometry)
                if feat.geometry is not None and not feat.geometry.is_empty
                else None
            )

            geom_type = feat.geometry.geom_type if feat.geometry is not None else "None"

            record = Feature(
                file_id=upload_record.id,
                feature_index=feat.index,
                geometry_type=geom_type,
                geometry=geom_geojson,
                crs=crs_str,
                properties=feat.properties,
                measurement_type=res.type,
                area_m2=res.value if res.type == "area" else None,
                length_m=res.value if res.type == "length" else None,
                geodesic_area_m2=res.geodesic_value if res.type == "area" else None,
                geodesic_length_m=res.geodesic_value if res.type == "length" else None,
                measurement_crs=res.measurement_crs,
                measurement_status=res.status,
                measurement_note=res.note,
            )
            feature_db_records.append(record)

        # Batch insert features into DB
        for i in range(0, len(feature_db_records), BATCH_SIZE):
            chunk = feature_db_records[i : i + BATCH_SIZE]
            db.add_all(chunk)
            db.flush()

        # Finalize upload record
        upload_record.feature_count = len(feature_db_records)
        upload_record.crs = crs_str
        upload_record.status = "COMPLETED"
        upload_record.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(upload_record)

        if extract_dir:
            cleanup_path(extract_dir)

        return upload_record

    except Exception as e:
        db.rollback()
        upload_record.status = "FAILED"
        upload_record.completed_at = datetime.now(UTC)
        if isinstance(e, AppError):
            upload_record.error_code = e.code
            upload_record.error_message = e.message
            e.details["id"] = upload_record.id
        else:
            upload_record.error_code = "INTERNAL_ERROR"
            upload_record.error_message = str(e)

        db.commit()

        if extract_dir:
            cleanup_path(extract_dir)

        raise e
