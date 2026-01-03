from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.database import Base

class UserSetting(Base):
    __tablename__ = "settings"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    value_type = Column(String, default="string")  # string, integer, boolean, json
    description = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
