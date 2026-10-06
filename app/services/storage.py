import shutil
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.core.errors import (
    FileTooLargeError,
    InvalidArchiveError,
    MissingCrsError,
    MissingShapefileComponentError,
    NoFileError,
    UnsupportedFileTypeError,
)

CHUNK_SIZE = 64 * 1024  # 64 KB streaming buffer


def validate_upload_filename(filename: str | None) -> tuple[str, str]:
    """
    Validate filename presence and extension.

    Returns:
        tuple[file_type, normalized_extension] where file_type is 'shapefile' or 'kml'.
    """
    if not filename or not filename.strip():
        raise NoFileError("No file or filename provided.")

    ext = Path(filename).suffix.lower()
    if ext == ".zip":
        return "shapefile", ".zip"
    elif ext == ".kml":
        return "kml", ".kml"
    else:
        raise UnsupportedFileTypeError("Only .zip (Shapefile) and .kml are supported.")


async def save_upload_stream(upload_file: UploadFile, dest_path: Path) -> int:
    """
    Stream and persist an uploaded file to disk while enforcing upload size limits.

    Raises:
        FileTooLargeError: If upload size exceeds MAX_UPLOAD_MB.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    total_bytes = 0

    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = await upload_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    f.close()
                    dest_path.unlink(missing_ok=True)
                    raise FileTooLargeError(settings.MAX_UPLOAD_MB)
                f.write(chunk)
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise

    return total_bytes


def is_ignored_path(path_str: str) -> bool:
    """Check if zip entry represents macOS metadata or hidden files."""
    parts = Path(path_str).parts
    for part in parts:
        if part == "__MACOSX" or part.startswith("."):
            return True
    return False


def extract_and_locate_shapefile(zip_path: Path, extract_dir: Path) -> Path:
    """
    Safely validate and extract a zip archive containing an ESRI Shapefile.
    Enforces zip-slip guards, zip-bomb size and count limits, and validates
    required companion files (.shp, .shx, .dbf, .prj).

    Returns:
        Path to the validated .shp file.
    """
    if not zipfile.is_zipfile(zip_path):
        raise InvalidArchiveError("Uploaded file is not a valid or readable zip archive.")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            infolist = zf.infolist()

            # Zip bomb checks
            if len(infolist) > settings.MAX_ZIP_FILES:
                raise InvalidArchiveError(
                    f"Archive exceeds maximum file count limit ({settings.MAX_ZIP_FILES} files)."
                )

            total_uncompressed_bytes = sum(info.file_size for info in infolist)
            max_uncompressed_bytes = settings.MAX_UNCOMPRESSED_MB * 1024 * 1024
            if total_uncompressed_bytes > max_uncompressed_bytes:
                raise InvalidArchiveError(
                    f"Archive uncompressed size exceeds limit of {settings.MAX_UNCOMPRESSED_MB} MB."
                )

            extract_dir.mkdir(parents=True, exist_ok=True)
            resolved_extract_dir = extract_dir.resolve()

            # Zip slip verification
            for member in infolist:
                member_path = resolved_extract_dir.joinpath(member.filename).resolve()
                if not member_path.is_relative_to(resolved_extract_dir):
                    raise InvalidArchiveError(
                        f"Zip slip security violation detected in entry: {member.filename}"
                    )

            # Perform extraction, skipping macOS artifacts and hidden files
            for member in infolist:
                if is_ignored_path(member.filename):
                    continue
                zf.extract(member, resolved_extract_dir)

    except zipfile.BadZipFile as e:
        raise InvalidArchiveError(f"Corrupted zip archive: {e}") from e

    # Find the primary .shp file
    shp_files = [
        f
        for f in extract_dir.rglob("*.shp")
        if not is_ignored_path(str(f.relative_to(extract_dir)))
    ]

    if not shp_files:
        raise MissingShapefileComponentError("Archive does not contain an ESRI Shapefile (.shp).")

    shp_path = shp_files[0]
    shp_stem = shp_path.stem
    parent_dir = shp_path.parent

    # Find companion files case-insensitively
    existing_files = {f.name.lower(): f for f in parent_dir.iterdir() if f.is_file()}

    shx_name = f"{shp_stem}.shx".lower()
    dbf_name = f"{shp_stem}.dbf".lower()
    prj_name = f"{shp_stem}.prj".lower()

    if shx_name not in existing_files:
        raise MissingShapefileComponentError(
            f"Shapefile '{shp_path.name}' is missing required index component (.shx)."
        )
    if dbf_name not in existing_files:
        raise MissingShapefileComponentError(
            f"Shapefile '{shp_path.name}' is missing required attribute component (.dbf)."
        )
    if prj_name not in existing_files:
        raise MissingCrsError(
            f"Shapefile '{shp_path.name}' is missing required coordinate reference projection (.prj)."
        )

    return shp_path


def cleanup_path(path: Path) -> None:
    """Safely remove a file or directory tree."""
    if path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
