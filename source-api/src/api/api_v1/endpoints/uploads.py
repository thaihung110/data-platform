import os
import uuid
from datetime import datetime
from typing import Optional

from config import settings
from dto.schemas import KafkaMessage, UploadResponse
from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from services.csv_processor import split_csv_by_rows, split_csv_by_size
from services.file_manager import get_chunk_path
from services.kafka_producer import kafka_service

router = APIRouter()


@router.post("/upload/csv", response_model=UploadResponse)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    chunk_size: Optional[int] = Form(settings.CHUNK_SIZE_MB),
    chunk_type: Optional[str] = Form(settings.CHUNK_TYPE),
    chunk_rows: Optional[int] = Form(settings.CHUNK_ROWS),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400, detail="Only CSV files are allowed"
        )

    # Processing logic
    if chunk_type == "size":
        chunks = await split_csv_by_size(file, dataset_name, chunk_size)
    elif chunk_type == "rows":
        chunks = await split_csv_by_rows(file, dataset_name, chunk_rows)
    else:
        raise HTTPException(
            status_code=400, detail="Invalid chunk_type. Use 'size' or 'rows'."
        )

    upload_id = chunks[0]["upload_id"] if chunks else str(uuid.uuid4())

    # Background task to publish metadata to Kafka
    background_tasks.add_task(publish_to_kafka, chunks, dataset_name)

    return UploadResponse(
        upload_id=upload_id,
        dataset_name=dataset_name,
        total_chunks=len(chunks),
        chunk_size=chunk_size if chunk_type == "size" else chunk_rows,
        chunk_unit="MB" if chunk_type == "size" else "rows",
        status="processing",
        tracking_url=f"/uploads/{upload_id}/status",
        created_at=datetime.utcnow(),
    )


async def publish_to_kafka(chunks: list, dataset_name: str):
    for chunk in chunks:
        message = KafkaMessage(
            upload_id=chunk["upload_id"],
            dataset_name=dataset_name,
            chunk_id=chunk["chunk_id"],
            filename=chunk["filename"],
            chunk_size_mb=chunk["chunk_size_mb"],
            row_count=chunk.get(
                "row_count", 0
            ),  # Use actual row count from chunk metadata
            file_path=chunk["file_path"],
            headers=chunk["headers"],
            published_at=datetime.utcnow(),
            api_endpoint=f"{settings.BASE_URL}/api/v1/chunks/{chunk['upload_id']}/{chunk['filename']}/download",
        )
        kafka_service.publish_chunk_metadata(message)
    kafka_service.flush()


@router.get("/chunks/{upload_id}/{filename}/download")
async def download_chunk(upload_id: str, filename: str):
    file_path = get_chunk_path(upload_id, filename)
    upload_dir = os.path.join(settings.TEMP_DIR, upload_id)

    # Debug logging
    print(f"📥 Download request received:")
    print(f"   upload_id: {upload_id}")
    print(f"   filename: {filename}")
    print(f"   full_path: {file_path}")
    print(f"   dir_exists: {os.path.exists(upload_dir)}")
    print(f"   file_exists: {os.path.exists(file_path)}")

    if os.path.exists(upload_dir):
        files_in_dir = os.listdir(upload_dir)
        print(f"   files_in_directory: {files_in_dir}")
        print(f"   total_files: {len(files_in_dir)}")
    else:
        print(f"   ❌ Directory does not exist!")

    if not os.path.exists(file_path):
        error_detail = {
            "error": "Chunk not found",
            "requested_file": filename,
            "upload_id": upload_id,
            "directory_exists": os.path.exists(upload_dir),
            "available_files": (
                os.listdir(upload_dir) if os.path.exists(upload_dir) else []
            ),
        }
        print(f"❌ File not found: {error_detail}")
        raise HTTPException(status_code=404, detail=str(error_detail))

    print(f"✅ Sending file: {filename}")
    return FileResponse(file_path, media_type="text/csv", filename=filename)
