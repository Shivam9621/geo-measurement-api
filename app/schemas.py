from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    id: str | None = None

    model_config = ConfigDict(extra="allow")


class ErrorResponse(BaseModel):
    error: ErrorDetail


class FileUploadResponse(BaseModel):
    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str


class FileDetailResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    feature_count: int
    crs: str | None
    status: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MeasurementValue(BaseModel):
    status: str
    type: str | None = None
    value: float | None = None
    unit: str | None = None
    also: dict[str, float] | None = None
    geodesic_value: float | None = None
    measurement_crs: str | None = None
    note: str | None = None


class FeatureItem(BaseModel):
    index: int
    geometry_type: str
    geometry: dict[str, Any] | None = None
    crs: str
    properties: dict[str, Any] = Field(default_factory=dict)
    measurement: MeasurementValue


class MeasurementResponse(BaseModel):
    file_id: str
    total: int
    limit: int
    offset: int
    features: list[FeatureItem]


class GeometryTypeCount(BaseModel):
    geometry_type: str
    count: int


class FileSummaryResponse(BaseModel):
    file_id: str
    filename: str
    status: str
    total_features: int
    total_area_m2: float
    total_length_m: float
    counts_by_geometry_type: dict[str, int]


class FileListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    files: list[FileDetailResponse]
