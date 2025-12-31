from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ModProfile(Base):
    __tablename__ = "mod_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    game_id = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True)
    
    mods = relationship("ProfileMod", back_populates="profile", cascade="all, delete-orphan")


class ProfileMod(Base):
    __tablename__ = "profile_mods"
    
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("mod_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    is_enabled = Column(Boolean, default=True)
    
    profile = relationship("ModProfile", back_populates="mods")
