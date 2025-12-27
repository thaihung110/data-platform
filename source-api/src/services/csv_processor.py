import csv
import os
import time
import uuid
from typing import List, Tuple

import aiofiles
from config import settings
from fastapi import UploadFile
from services.file_manager import save_chunk


async def split_csv_by_size(
    file: UploadFile, dataset_name: str, chunk_size_mb: int
) -> List[dict]:
    """
    Stream large CSV file and split by file size.
    """
    chunk_size_bytes = chunk_size_mb * 1024 * 1024
    upload_id = str(uuid.uuid4())
    chunks_metadata = []

    # Read headers
    header_line = await file.read(65536)  # Read a buffer for header
    first_newline = header_line.find(b"\n")
    if first_newline == -1:
        # Re-read or handle very long headers if necessary
        headers = []
    else:
        headers = header_line[:first_newline].decode().strip().split(",")
        # Reset file pointer to after headers for content reading
        await file.seek(first_newline + 1)

    chunk_id = 1
    buffer = b""

    while True:
        chunk_data = await file.read(chunk_size_bytes)
        if not chunk_data:
            break

        # Find the last newline to avoid splitting a row
        last_newline = chunk_data.rfind(b"\n")
        if last_newline != -1:
            to_write = chunk_data[: last_newline + 1]
            buffer = chunk_data[last_newline + 1 :]
        else:
            # If no newline in this chunk, we need to read more
            buffer += chunk_data
            continue

        filename = f"{dataset_name}_{chunk_id}_{int(time.time()*1000)}.csv"
        # Prepend headers to each chunk
        content = (",".join(headers) + "\n").encode() + to_write
        row_count = to_write.count(b"\n")  # Count rows in chunk

        file_path = await save_chunk(upload_id, filename, content)

        chunks_metadata.append(
            {
                "upload_id": upload_id,
                "chunk_id": chunk_id,
                "filename": filename,
                "file_path": file_path,
                "headers": headers,
                "chunk_size_mb": len(content) / (1024 * 1024),
                "row_count": row_count,
            }
        )
        chunk_id += 1

    # Handle remaining buffer
    if buffer:
        filename = f"{dataset_name}_{chunk_id}_{int(time.time()*1000)}.csv"
        content = (",".join(headers) + "\n").encode() + buffer
        row_count = buffer.count(b"\n")  # Count rows in remaining buffer
        file_path = await save_chunk(upload_id, filename, content)
        chunks_metadata.append(
            {
                "upload_id": upload_id,
                "chunk_id": chunk_id,
                "filename": filename,
                "file_path": file_path,
                "headers": headers,
                "chunk_size_mb": len(content) / (1024 * 1024),
                "row_count": row_count,
            }
        )

    return chunks_metadata


async def split_csv_by_rows(
    file: UploadFile, dataset_name: str, rows_per_chunk: int
) -> List[dict]:
    """
    Stream CSV and group by row count.
    """
    upload_id = str(uuid.uuid4())
    chunks_metadata = []

    # Simple line-by-line reading for row-based splitting
    # Note: For very large files, aiofiles might be better but standard file.file is a SpooledTemporaryFile
    # which is already in memory or on disk.

    content_iter = iter(file.file)
    try:
        header_line = next(content_iter).decode().strip()
        headers = header_line.split(",")
    except StopIteration:
        return []

    chunk_id = 1
    current_rows = []

    for line in content_iter:
        current_rows.append(line.decode())
        if len(current_rows) >= rows_per_chunk:
            filename = f"{dataset_name}_{chunk_id}_{int(time.time()*1000)}.csv"
            content = (header_line + "\n" + "".join(current_rows)).encode()
            file_path = await save_chunk(upload_id, filename, content)

            chunks_metadata.append(
                {
                    "upload_id": upload_id,
                    "chunk_id": chunk_id,
                    "filename": filename,
                    "file_path": file_path,
                    "headers": headers,
                    "chunk_size_mb": len(content) / (1024 * 1024),
                    "row_count": len(current_rows),
                }
            )
            chunk_id += 1
            current_rows = []

    if current_rows:
        filename = f"{dataset_name}_{chunk_id}_{int(time.time()*1000)}.csv"
        content = (header_line + "\n" + "".join(current_rows)).encode()
        file_path = await save_chunk(upload_id, filename, content)
        chunks_metadata.append(
            {
                "upload_id": upload_id,
                "chunk_id": chunk_id,
                "filename": filename,
                "file_path": file_path,
                "headers": headers,
                "chunk_size_mb": len(content) / (1024 * 1024),
                "row_count": len(current_rows),
            }
        )

    return chunks_metadata
