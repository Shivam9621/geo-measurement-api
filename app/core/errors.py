class AppError(Exception):
    """Base application exception with standardized API error shape."""

    def __init__(
        self, code: str, message: str, status_code: int = 400, details: dict | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NoFileError(AppError):
    def __init__(self, message: str = "No file was uploaded."):
        super().__init__(code="NO_FILE", message=message, status_code=400)


class UnsupportedFileTypeError(AppError):
    def __init__(self, message: str = "Only .zip (Shapefile) and .kml are supported."):
        super().__init__(code="UNSUPPORTED_FILE_TYPE", message=message, status_code=400)


class FileTooLargeError(AppError):
    def __init__(self, max_mb: int = 50):
        super().__init__(
            code="FILE_TOO_LARGE",
            message=f"Uploaded file exceeds maximum allowed limit of {max_mb} MB.",
            status_code=413,
        )


class InvalidArchiveError(AppError):
    def __init__(
        self, message: str = "Zip archive is invalid, corrupted, or violates security policies."
    ):
        super().__init__(code="INVALID_ARCHIVE", message=message, status_code=422)


class MissingShapefileComponentError(AppError):
    def __init__(
        self, message: str = "Shapefile is missing required components (.shp, .shx, or .dbf)."
    ):
        super().__init__(code="MISSING_SHAPEFILE_COMPONENT", message=message, status_code=422)


class MissingCrsError(AppError):
    def __init__(self, message: str = "Shapefile is missing required projection component (.prj)."):
        super().__init__(code="MISSING_CRS", message=message, status_code=422)


class InvalidGeospatialFileError(AppError):
    def __init__(self, message: str = "Geospatial file could not be parsed."):
        super().__init__(code="INVALID_GEOSPATIAL_FILE", message=message, status_code=422)


class NoFeaturesError(AppError):
    def __init__(self, message: str = "Geospatial file contains no features."):
        super().__init__(code="NO_FEATURES", message=message, status_code=422)


class FileNotFoundError(AppError):
    def __init__(self, file_id: str):
        super().__init__(
            code="FILE_NOT_FOUND", message=f"File with id '{file_id}' not found.", status_code=404
        )


class FileProcessingFailedError(AppError):
    def __init__(self, message: str = "File processing failed."):
        super().__init__(code="FILE_PROCESSING_FAILED", message=message, status_code=409)


class FileNotReadyError(AppError):
    def __init__(self, message: str = "File processing is still in progress."):
        super().__init__(code="FILE_NOT_READY", message=message, status_code=409)
