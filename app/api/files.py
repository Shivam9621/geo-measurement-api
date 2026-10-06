import uuid
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError, NoFileError
from app.database import get_db
from app.models import UploadedFile
from app.services.storage import (
    cleanup_path,
    extract_and_locate_shapefile,
    save_upload_stream,
    validate_upload_filename,
)

router = APIRouter(prefix="/api/files", tags=["Files"])


@router.post("/", status_code=201)
async def upload_file(
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Upload and validate a geospatial file (.zip containing Shapefile or .kml)."""
    if file is None:
        raise NoFileError("No file provided in the upload request.")

    file_type, ext = validate_upload_filename(file.filename)
    file_id = uuid.uuid4().hex

    file_dir = settings.UPLOAD_DIR / file_id
    dest_path = file_dir / f"original{ext}"
    extract_dir = file_dir / "extracted"

    # Create initial DB record in PROCESSING state
    uploaded_record = UploadedFile(
        id=file_id,
        filename=file.filename or f"uploaded{ext}",
        file_type=file_type,
        status="PROCESSING",
    )
    db.add(uploaded_record)
    db.commit()

    try:
        # Stream file to disk enforcing max size
        await save_upload_stream(file, dest_path)

        # Validate archive structure for shapefiles
        if file_type == "shapefile":
            extract_and_locate_shapefile(dest_path, extract_dir)

        # In M2, we verify storage plumbing. (Full pipeline is connected in M5)
        return JSONResponse(
            status_code=201,
            content={
                "id": file_id,
                "filename": uploaded_record.filename,
                "feature_count": 0,
                "crs": None,
                "status": "PROCESSING",
            },
        )
    except AppError as e:
        uploaded_record.status = "FAILED"
        uploaded_record.error_code = e.code
        uploaded_record.error_message = e.message
        db.commit()
        cleanup_path(extract_dir)
        e.details["id"] = file_id
        raise e
    except Exception as e:
        uploaded_record.status = "FAILED"
        uploaded_record.error_code = "INTERNAL_ERROR"
        uploaded_record.error_message = str(e)
        db.commit()
        cleanup_path(extract_dir)
        raise e
