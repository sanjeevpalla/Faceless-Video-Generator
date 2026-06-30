import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, JSON, Enum, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class LogLevel(str, PyEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Log(Base):
    __tablename__ = "logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    level = Column(Enum(LogLevel), nullable=False, default=LogLevel.INFO, index=True)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    context = Column(JSON, nullable=False, default=dict)
    source = Column(String(255), nullable=True)
    job_id = Column(String(36), nullable=True, index=True)

    # Relationships
    project = relationship("Project", back_populates="logs")

    def __repr__(self) -> str:
        return f"<Log id={self.id} level={self.level} message={self.message[:50]!r}>"
