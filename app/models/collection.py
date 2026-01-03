from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Collection(Base):
    __tablename__ = "collections"
    
    id = Column(Integer, primary_key=True, index=True)
    nexus_collection_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=False)
    author = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    game_id = Column(String, nullable=False, index=True)
    version = Column(String, nullable=True)
    mod_count = Column(Integer, default=0)
    thumbnail_url = Column(String, nullable=True)
    nexus_url = Column(String, nullable=True)
    collection_data = Column(JSON, nullable=True)
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    installed_at = Column(DateTime(timezone=True), nullable=True)
    
    mods = relationship("CollectionMod", back_populates="collection", cascade="all, delete-orphan")


class CollectionMod(Base):
    __tablename__ = "collection_mods"
    
    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    nexus_mod_id = Column(Integer, nullable=False)
    nexus_file_id = Column(Integer, nullable=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="SET NULL"), nullable=True)
    is_required = Column(Boolean, default=True)
    install_order = Column(Integer, nullable=True)
    installer_choices = Column(JSON, nullable=True)  # Pre-saved FOMOD choices from collection curator
    
    collection = relationship("Collection", back_populates="mods")
