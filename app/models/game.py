from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Game(Base):
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    game_id = Column(String, nullable=False, unique=True, index=True)
    version = Column(String, nullable=True)
    install_path = Column(String, nullable=False)
    launcher_type = Column(String, nullable=False)  # steam, gog, epic, standalone
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
