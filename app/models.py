from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """Return current UTC datetime with timezone awareness."""
    return datetime.now(UTC)


class UploadedFile(Base):
    """Uploaded geospatial file tracking record."""

    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # shapefile or kml
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PROCESSING"
    )  # PROCESSING, COMPLETED, FAILED
    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    features: Mapped[list["Feature"]] = relationship(
        "Feature",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Feature(Base):
    """Extracted feature record with computed projected and geodesic measurements."""

    __tablename__ = "features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    crs: Mapped[str] = mapped_column(String(100), nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    measurement_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # area, length, or None
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    geodesic_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    geodesic_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    measurement_status: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # OK, NOT_APPLICABLE, UNSUPPORTED, INVALID, EMPTY, ERROR
    measurement_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped["UploadedFile"] = relationship("UploadedFile", back_populates="features")
