from datetime import datetime

from db.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class Upload(Base):
    """
    Database Model for Upload tracking.
    Maps to the 'uploads' table in PostgreSQL.
    """

    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(String, unique=True, index=True, nullable=False)
    dataset_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    total_chunks = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
