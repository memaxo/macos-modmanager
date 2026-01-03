"""
Compatibility Database Models

Models for tracking mod compatibility on macOS.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SQLEnum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum
from typing import Optional
from datetime import datetime

from app.database import Base


class CompatibilityStatus(str, Enum):
    """Compatibility status values"""
    WORKS = "works"              # Fully functional
    PARTIAL = "partial"          # Some features work
    BROKEN = "broken"            # Does not work
    WINDOWS_ONLY = "windows_only"  # Cannot work on macOS (requires Windows-only features)
    UNKNOWN = "unknown"          # Not tested


class ModCompatibilityReport(Base):
    """
    Community-reported mod compatibility for macOS.
    
    Each report represents a user's test of a specific mod version.
    """
    __tablename__ = "mod_compatibility_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Mod identification
    nexus_mod_id = Column(Integer, index=True, nullable=False)
    mod_name = Column(String(255), nullable=False)
    mod_version = Column(String(50), nullable=True)
    
    # Compatibility info
    status = Column(SQLEnum(CompatibilityStatus), default=CompatibilityStatus.UNKNOWN)
    macos_port_url = Column(String(512), nullable=True)  # URL to macOS port if available
    
    # Test environment
    tested_game_version = Column(String(50), nullable=True)
    tested_red4ext_version = Column(String(50), nullable=True)
    tested_macos_version = Column(String(50), nullable=True)
    
    # Report details
    tested_by = Column(String(100), nullable=False, default="anonymous")
    notes = Column(Text, nullable=True)
    
    # Voting
    votes_up = Column(Integer, default=0)
    votes_down = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    alternatives = relationship("CompatibilityAlternative", back_populates="broken_mod_report", foreign_keys="CompatibilityAlternative.broken_mod_report_id")
    
    @property
    def confidence_score(self) -> float:
        """Calculate confidence score based on votes"""
        total_votes = self.votes_up + self.votes_down
        if total_votes == 0:
            return 0.5
        return self.votes_up / total_votes
    
    @property
    def is_reliable(self) -> bool:
        """Check if report has enough votes to be reliable"""
        return (self.votes_up + self.votes_down) >= 3


class CompatibilityAlternative(Base):
    """
    Suggests alternative mods for broken ones.
    
    When a mod doesn't work on macOS, this tracks alternatives that do.
    """
    __tablename__ = "compatibility_alternatives"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to broken mod report
    broken_mod_report_id = Column(Integer, ForeignKey("mod_compatibility_reports.id"), nullable=False)
    broken_mod_report = relationship("ModCompatibilityReport", back_populates="alternatives", foreign_keys=[broken_mod_report_id])
    
    # Alternative mod info
    alternative_nexus_mod_id = Column(Integer, nullable=False)
    alternative_mod_name = Column(String(255), nullable=False)
    alternative_mod_url = Column(String(512), nullable=True)
    
    # Why it's a good alternative
    reason = Column(Text, nullable=True)
    similarity_score = Column(Integer, default=50)  # 0-100, how similar the functionality is
    
    # Voting
    votes_up = Column(Integer, default=0)
    votes_down = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CompatibilityVote(Base):
    """
    Tracks individual votes on compatibility reports.
    
    Prevents duplicate voting from the same user.
    """
    __tablename__ = "compatibility_votes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # What was voted on
    report_id = Column(Integer, ForeignKey("mod_compatibility_reports.id"), nullable=True)
    alternative_id = Column(Integer, ForeignKey("compatibility_alternatives.id"), nullable=True)
    
    # Voter identification (simple for now, could be enhanced)
    voter_id = Column(String(100), nullable=False)  # Could be session ID, IP hash, etc.
    
    # Vote type
    is_upvote = Column(Boolean, nullable=False)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KnownMacOSMod(Base):
    """
    Known mods that have been ported to macOS.
    
    This is a curated list of mods we know work on macOS.
    """
    __tablename__ = "known_macos_mods"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Mod identification
    name = Column(String(255), nullable=False, unique=True)
    nexus_mod_id = Column(Integer, nullable=True, index=True)
    
    # macOS port info
    github_url = Column(String(512), nullable=True)
    download_url = Column(String(512), nullable=True)
    latest_version = Column(String(50), nullable=True)
    
    # Status
    is_framework = Column(Boolean, default=False)  # Is this a core framework (RED4ext, TweakXL, etc.)
    is_verified = Column(Boolean, default=False)   # Has been verified by maintainers
    
    # Description
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
