from datetime import datetime

from sqlalchemy import Column, String, DateTime, JSON

from app.database import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True, index=True)
    value = Column(JSON, nullable=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    description = Column(String(1024), nullable=True)
    category = Column(String(100), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r}>"
