from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    DATABASE_URL: str = Field(default="sqlite:///./geo.db", description="Database connection URL")
    UPLOAD_DIR: Path = Field(
        default=Path("./uploads"), description="Directory to store uploaded files"
    )
    MAX_UPLOAD_MB: int = Field(default=50, description="Max allowed upload size in megabytes")
    MAX_ZIP_FILES: int = Field(
        default=50, description="Max allowed files inside an uploaded zip archive"
    )
    MAX_UNCOMPRESSED_MB: int = Field(
        default=500, description="Max allowed total uncompressed size in MB"
    )
    ALLOWED_EXTENSIONS: list[str] = Field(
        default=[".zip", ".kml"], description="Allowed file extensions (lowercase)"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
