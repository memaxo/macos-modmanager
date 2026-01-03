"""
Backup Database Models

Models for tracking mod backups and snapshots.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, BigInteger
from sqlalchemy.sql import func
from enum import Enum
from datetime import datetime

from app.database import Base


class BackupType(str, Enum):
    """Types of backups"""
    FULL = "full"              # Complete mod folder backup
    INCREMENTAL = "incremental"  # Only changed files
    MOD_SPECIFIC = "mod_specific"  # Single mod backup
    PRE_INSTALL = "pre_install"   # Before mod installation
    PRE_UPDATE = "pre_update"     # Before framework update
    SCHEDULED = "scheduled"       # Scheduled automatic backup
    MANUAL = "manual"            # User-requested backup


class BackupStatus(str, Enum):
    """Backup status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTORING = "restoring"
    RESTORED = "restored"


class Backup(Base):
    """
    Represents a backup snapshot of the mod installation.
    """
    __tablename__ = "backups"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Backup identification
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    backup_type = Column(String(50), default=BackupType.MANUAL.value)
    
    # Status
    status = Column(String(50), default=BackupStatus.PENDING.value)
    error_message = Column(Text, nullable=True)
    
    # Storage info
    backup_path = Column(String(512), nullable=False)
    manifest_path = Column(String(512), nullable=True)
    size_bytes = Column(BigInteger, default=0)
    file_count = Column(Integer, default=0)
    
    # Compression
    is_compressed = Column(Boolean, default=True)
    compression_ratio = Column(Integer, default=0)  # Percentage
    
    # What was backed up
    includes_frameworks = Column(Boolean, default=True)
    includes_plugins = Column(Boolean, default=True)
    includes_scripts = Column(Boolean, default=True)
    includes_tweaks = Column(Boolean, default=True)
    includes_archives = Column(Boolean, default=False)
    
    # Related mod (for mod-specific backups)
    mod_id = Column(Integer, nullable=True)
    mod_name = Column(String(255), nullable=True)
    
    # Game version at backup time
    game_version = Column(String(50), nullable=True)
    red4ext_version = Column(String(50), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Restore info
    last_restored_at = Column(DateTime(timezone=True), nullable=True)
    restore_count = Column(Integer, default=0)
    
    @property
    def size_mb(self) -> float:
        """Get size in MB"""
        return self.size_bytes / (1024 * 1024) if self.size_bytes else 0
    
    @property
    def is_restorable(self) -> bool:
        """Check if backup can be restored"""
        return self.status == BackupStatus.COMPLETED.value


class BackupSettings(Base):
    """
    User settings for backup behavior.
    """
    __tablename__ = "backup_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Auto-backup settings
    auto_backup_enabled = Column(Boolean, default=True)
    backup_before_install = Column(Boolean, default=True)
    backup_before_update = Column(Boolean, default=True)
    
    # Scheduled backups
    scheduled_backup_enabled = Column(Boolean, default=False)
    schedule_interval_hours = Column(Integer, default=24)
    
    # Retention
    max_backups_to_keep = Column(Integer, default=10)
    max_backup_age_days = Column(Integer, default=30)
    max_storage_mb = Column(Integer, default=5000)  # 5GB default
    
    # What to back up by default
    default_include_frameworks = Column(Boolean, default=True)
    default_include_plugins = Column(Boolean, default=True)
    default_include_scripts = Column(Boolean, default=True)
    default_include_tweaks = Column(Boolean, default=True)
    default_include_archives = Column(Boolean, default=False)
    
    # Compression
    enable_compression = Column(Boolean, default=True)
    
    # Updated timestamp
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
