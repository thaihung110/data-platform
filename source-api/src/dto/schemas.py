import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    upload_id: str
    dataset_name: str
    total_chunks: int
    chunk_size: Optional[int]
    chunk_unit: str
    status: str
    tracking_url: str
    created_at: datetime


class KafkaMessage(BaseModel):
    upload_id: str
    dataset_name: str
    chunk_id: int
    filename: str
    chunk_size_mb: float
    row_count: int
    file_path: Optional[str] = None
    headers: List[str]
    published_at: datetime
    api_endpoint: str
