from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Mod(Base):
    __tablename__ = "mods"
    
    id = Column(Integer, primary_key=True, index=True)
    nexus_mod_id = Column(Integer, unique=True, index=True, nullable=True)
    name = Column(String, nullable=False)
    author = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    version = Column(String, nullable=True)
    game_id = Column(String, nullable=False, index=True)
    mod_type = Column(String, nullable=True)  # redscript, archive, redmod, mixed
    install_path = Column(String, nullable=False)
    file_hash = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    download_url = Column(String, nullable=True)
    nexus_url = Column(String, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True, index=True)
    is_active = Column(Boolean, default=True, index=True)
    install_date = Column(DateTime(timezone=True), server_default=func.now())
    update_date = Column(DateTime(timezone=True), nullable=True)
    last_checked = Column(DateTime(timezone=True), nullable=True)
    mod_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata' (reserved in SQLAlchemy)
    
    # Relationships
    files = relationship("ModFile", back_populates="mod", cascade="all, delete-orphan")
    dependencies = relationship("ModDependency", back_populates="mod", cascade="all, delete-orphan")


class ModFile(Base):
    __tablename__ = "mod_files"
    
    id = Column(Integer, primary_key=True, index=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)
    file_hash = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    install_path = Column(String, nullable=True, index=True)
    
    mod = relationship("Mod", back_populates="files")


class ModDependency(Base):
    __tablename__ = "mod_dependencies"
    
    id = Column(Integer, primary_key=True, index=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    dependency_name = Column(String, nullable=False, index=True)
    dependency_type = Column(String, nullable=False)  # required, optional, incompatible
    min_version = Column(String, nullable=True)
    max_version = Column(String, nullable=True)
    nexus_mod_id = Column(Integer, nullable=True)
    is_satisfied = Column(Boolean, default=False, index=True)
    
    mod = relationship("Mod", back_populates="dependencies")
