from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, computed_field

from app.models.enums import AssetType


class AssetResponse(BaseModel):
    id: UUID
    test_version_id: UUID
    asset_type: AssetType
    relative_path: str
    mime_type: str
    original_name: str
    file_size: int
    created_at: datetime

    @computed_field
    @property
    def content_url(self) -> str:
        return f"/assets/{self.id}/content"
