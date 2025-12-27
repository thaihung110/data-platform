import os

import aiofiles
from config import settings


async def save_chunk(upload_id: str, filename: str, content: bytes) -> str:
    """
    Save chunk content to temporary storage.
    """
    upload_dir = os.path.join(settings.TEMP_DIR, upload_id)
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir, exist_ok=True)
        print(f"📁 Created directory: {upload_dir}")

    file_path = os.path.join(upload_dir, filename)
    print(f"💾 Saving chunk: {filename} ({len(content)} bytes)")

    async with aiofiles.open(file_path, mode="wb") as f:
        await f.write(content)

    # Verify file was created
    if os.path.exists(file_path):
        actual_size = os.path.getsize(file_path)
        print(
            f"✅ File saved successfully: {filename}, size: {actual_size} bytes"
        )
    else:
        print(f"❌ ERROR: File NOT found after save: {filename}")

    return file_path


def get_chunk_path(upload_id: str, chunk_filename: str) -> str:
    return os.path.join(settings.TEMP_DIR, upload_id, chunk_filename)
