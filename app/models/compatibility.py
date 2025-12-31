from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base


class CompatibilityRule(Base):
    __tablename__ = "compatibility_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=True, index=True)
    nexus_mod_id = Column(Integer, nullable=True, index=True)
    rule_type = Column(String, nullable=False, index=True)  # compatible, incompatible, requires, conflicts_with
    target_mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=True)
    target_nexus_mod_id = Column(Integer, nullable=True)
    target_dependency = Column(String, nullable=True)  # e.g., ArchiveXL, Codeware
    platform = Column(String, nullable=True, index=True)  # macos, windows, linux
    game_version_min = Column(String, nullable=True)
    game_version_max = Column(String, nullable=True)
    severity = Column(String, default="warning", index=True)  # critical, warning, info
    description = Column(Text, nullable=True)
    source = Column(String, default="user")  # user, community, official, auto
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    verified = Column(Boolean, default=False)


class ModConflict(Base):
    __tablename__ = "mod_conflicts"
    
    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False, index=True)
    mod_id_1 = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    mod_id_2 = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    conflict_type = Column(String, nullable=False)  # file_overwrite, load_order, incompatible
    severity = Column(String, nullable=False, index=True)  # critical, warning, info
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved = Column(Boolean, default=False, index=True)
    resolution_method = Column(String, nullable=True)
    
    __table_args__ = (
        CheckConstraint('mod_id_1 != mod_id_2', name='check_different_mods'),
    )
