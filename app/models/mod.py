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
    dependencies = relationship("ModDependency", back_populates="mod", cascade="all, delete-orphan", foreign_keys="ModDependency.mod_id")
    installations = relationship("ModInstallation", back_populates="mod", cascade="all, delete-orphan")


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
    target_mod_id = Column(Integer, ForeignKey("mods.id", ondelete="SET NULL"), nullable=True)
    is_satisfied = Column(Boolean, default=False, index=True)
    
    mod = relationship("Mod", back_populates="dependencies", foreign_keys=[mod_id])
    target_mod = relationship("Mod", foreign_keys=[target_mod_id])


class ModInstallation(Base):
    __tablename__ = "mod_installations"
    
    id = Column(Integer, primary_key=True, index=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    install_type = Column(String, nullable=False)  # install, update, uninstall
    backup_path = Column(String, nullable=True)
    install_path = Column(String, nullable=False)
    file_hash_before = Column(String, nullable=True)
    file_hash_after = Column(String, nullable=True)
    installed_at = Column(DateTime(timezone=True), server_default=func.now())
    rollback_available = Column(Boolean, default=False, index=True)
    
    mod = relationship("Mod", back_populates="installations")


class Wishlist(Base):
    __tablename__ = "wishlist"
    
    id = Column(Integer, primary_key=True, index=True)
    nexus_mod_id = Column(Integer, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    author = Column(String, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())


class ModInstallerChoices(Base):
    """Stores FOMOD installer choices for a mod installation"""
    __tablename__ = "mod_installer_choices"
    
    id = Column(Integer, primary_key=True, index=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    installer_type = Column(String, nullable=False)  # "fomod", "manual", etc.
    choices_data = Column(JSON, nullable=False)  # Stored choices in Vortex-compatible format
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    mod = relationship("Mod")
