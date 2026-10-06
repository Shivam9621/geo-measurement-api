import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import (
    AppError,
    FileNotFoundError,
    FileNotReadyError,
    FileProcessingFailedError,
    NoFileError,
)
from app.database import get_db
from app.models import Feature, UploadedFile
from app.schemas import (
    FeatureItem,
    FileDetailResponse,
    FileListResponse,
    FileSummaryResponse,
    FileUploadResponse,
    MeasurementResponse,
    MeasurementValue,
)
from app.services.processing import process_file
from app.services.storage import (
    cleanup_path,
    save_upload_stream,
    validate_upload_filename,
)

router = APIRouter(prefix="/api/files", tags=["Files"])


@router.post("/", response_model=FileUploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Upload and process a geospatial file (.zip containing Shapefile or .kml)."""
    if file is None:
        raise NoFileError("No file provided in the upload request.")

    file_type, ext = validate_upload_filename(file.filename)
    file_id = uuid.uuid4().hex

    file_dir = settings.UPLOAD_DIR / file_id
    dest_path = file_dir / f"original{ext}"

    # Initialize tracking record
    uploaded_record = UploadedFile(
        id=file_id,
        filename=file.filename or f"uploaded{ext}",
        file_type=file_type,
        status="PROCESSING",
    )
    db.add(uploaded_record)
    db.commit()

    try:
        # Stream file to disk while enforcing max upload size
        await save_upload_stream(file, dest_path)

        # Synchronous full processing pipeline
        completed_record = process_file(
            upload_record=uploaded_record,
            file_path=dest_path,
            file_type=file_type,
            db=db,
        )

        return JSONResponse(
            status_code=201,
            content={
                "id": completed_record.id,
                "filename": completed_record.filename,
                "feature_count": completed_record.feature_count,
                "crs": completed_record.crs,
                "status": completed_record.status,
            },
        )
    except AppError as e:
        # Error details already attached by process_file
        raise e
    except Exception as e:
        raise e


@router.get("/", response_model=FileListResponse)
def list_files(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> FileListResponse:
    """Retrieve a paginated list of all uploaded files."""
    total = db.scalar(select(func.count(UploadedFile.id))) or 0
    query = (
        select(UploadedFile).order_by(UploadedFile.created_at.desc()).offset(offset).limit(limit)
    )
    records = db.scalars(query).all()

    return FileListResponse(
        total=total,
        limit=limit,
        offset=offset,
        files=[FileDetailResponse.model_validate(r) for r in records],
    )


@router.get("/{file_id}/", response_model=FileDetailResponse)
def get_file_info(file_id: str, db: Session = Depends(get_db)) -> FileDetailResponse:
    """Retrieve metadata and status for a specific file upload."""
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise FileNotFoundError(file_id)

    return FileDetailResponse.model_validate(record)


@router.get("/{file_id}/measurements/", response_model=MeasurementResponse)
def get_file_measurements(
    file_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    geometry_type: str | None = Query(default=None, description="Optional filter by geometry type"),
    include_geometry: bool = Query(default=True, description="Whether to include GeoJSON geometry"),
    db: Session = Depends(get_db),
) -> MeasurementResponse:
    """Retrieve calculated feature measurements with pagination and filtering."""
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise FileNotFoundError(file_id)

    if record.status == "FAILED":
        raise FileProcessingFailedError(record.error_message or "File processing failed.")
    elif record.status == "PROCESSING":
        raise FileNotReadyError("File processing is still in progress.")

    base_stmt = select(Feature).where(Feature.file_id == file_id)
    if geometry_type:
        base_stmt = base_stmt.where(Feature.geometry_type.ilike(geometry_type))

    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    paged_stmt = base_stmt.order_by(Feature.feature_index.asc()).offset(offset).limit(limit)
    feature_records = db.scalars(paged_stmt).all()

    items: list[FeatureItem] = []
    for f in feature_records:
        also_dict: dict[str, float] | None = None
        if f.measurement_type == "area" and f.area_m2 is not None:
            also_dict = {
                "hectares": round(f.area_m2 / 10000.0, 4),
                "sq_km": round(f.area_m2 / 1000000.0, 4),
            }
        elif f.measurement_type == "length" and f.length_m is not None:
            also_dict = {
                "km": round(f.length_m / 1000.0, 4),
            }

        val = f.area_m2 if f.measurement_type == "area" else f.length_m
        unit = (
            "m2"
            if f.measurement_type == "area"
            else ("m" if f.measurement_type == "length" else None)
        )
        geodesic_val = f.geodesic_area_m2 if f.measurement_type == "area" else f.geodesic_length_m

        measurement = MeasurementValue(
            status=f.measurement_status,
            type=f.measurement_type,
            value=val,
            unit=unit,
            also=also_dict,
            geodesic_value=geodesic_val,
            measurement_crs=f.measurement_crs,
            note=f.measurement_note,
        )

        item = FeatureItem(
            index=f.feature_index,
            geometry_type=f.geometry_type,
            geometry=f.geometry if include_geometry else None,
            crs=f.crs,
            properties=f.properties,
            measurement=measurement,
        )
        items.append(item)

    return MeasurementResponse(
        file_id=file_id,
        total=total,
        limit=limit,
        offset=offset,
        features=items,
    )


@router.get("/{file_id}/summary/", response_model=FileSummaryResponse)
def get_file_summary(file_id: str, db: Session = Depends(get_db)) -> FileSummaryResponse:
    """Retrieve statistical summary for all features in the file."""
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise FileNotFoundError(file_id)

    if record.status == "FAILED":
        raise FileProcessingFailedError(record.error_message or "File processing failed.")
    elif record.status == "PROCESSING":
        raise FileNotReadyError("File processing is still in progress.")

    features = db.scalars(select(Feature).where(Feature.file_id == file_id)).all()

    total_area = sum(f.area_m2 or 0.0 for f in features if f.measurement_type == "area")
    total_length = sum(f.length_m or 0.0 for f in features if f.measurement_type == "length")

    counts: dict[str, int] = defaultdict(int)
    for f in features:
        counts[f.geometry_type] += 1

    return FileSummaryResponse(
        file_id=file_id,
        filename=record.filename,
        status=record.status,
        total_features=len(features),
        total_area_m2=round(total_area, 2),
        total_length_m=round(total_length, 2),
        counts_by_geometry_type=dict(counts),
    )


@router.delete("/{file_id}/", status_code=204)
def delete_file(file_id: str, db: Session = Depends(get_db)) -> Response:
    """Delete uploaded file, its extracted records, and files on disk."""
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise FileNotFoundError(file_id)

    # Delete database record (cascades to features)
    db.delete(record)
    db.commit()

    # Clean up directory on disk
    file_dir = settings.UPLOAD_DIR / file_id
    cleanup_path(file_dir)

    return Response(status_code=204)
