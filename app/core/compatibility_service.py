"""
Compatibility Service

Service layer for querying and managing mod compatibility data.
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import datetime

from app.models.compatibility_db import (
    ModCompatibilityReport,
    CompatibilityAlternative,
    CompatibilityVote,
    KnownMacOSMod,
    CompatibilityStatus,
)


class CompatibilityService:
    """
    Service for managing mod compatibility data.
    
    Provides methods to:
    - Query compatibility by mod ID
    - Aggregate community reports
    - Calculate confidence scores
    - Find alternatives for broken mods
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # ============================================================
    # Query Methods
    # ============================================================
    
    def get_compatibility(self, nexus_mod_id: int) -> Optional[Dict[str, Any]]:
        """
        Get aggregated compatibility info for a mod.
        
        Args:
            nexus_mod_id: Nexus Mods mod ID
            
        Returns:
            Aggregated compatibility data or None
        """
        reports = self.db.query(ModCompatibilityReport).filter(
            ModCompatibilityReport.nexus_mod_id == nexus_mod_id
        ).all()
        
        if not reports:
            # Check if it's a known macOS mod
            known = self.db.query(KnownMacOSMod).filter(
                KnownMacOSMod.nexus_mod_id == nexus_mod_id
            ).first()
            
            if known:
                return {
                    "nexus_mod_id": nexus_mod_id,
                    "status": CompatibilityStatus.WORKS.value,
                    "confidence": 1.0,
                    "is_known_port": True,
                    "port_url": known.github_url or known.download_url,
                    "reports": [],
                }
            
            return None
        
        # Aggregate reports
        status_votes = {}
        for report in reports:
            weight = report.votes_up - report.votes_down + 1
            status = report.status.value
            status_votes[status] = status_votes.get(status, 0) + weight
        
        # Determine most likely status
        if status_votes:
            best_status = max(status_votes, key=status_votes.get)
        else:
            best_status = CompatibilityStatus.UNKNOWN.value
        
        # Calculate confidence
        total_votes = sum(r.votes_up + r.votes_down for r in reports)
        reliable_reports = [r for r in reports if r.is_reliable]
        confidence = len(reliable_reports) / len(reports) if reports else 0
        
        # Check for macOS port
        port_url = None
        for report in reports:
            if report.macos_port_url:
                port_url = report.macos_port_url
                break
        
        return {
            "nexus_mod_id": nexus_mod_id,
            "mod_name": reports[0].mod_name if reports else None,
            "status": best_status,
            "confidence": confidence,
            "total_reports": len(reports),
            "total_votes": total_votes,
            "is_known_port": False,
            "port_url": port_url,
            "reports": [
                {
                    "id": r.id,
                    "status": r.status.value,
                    "version": r.mod_version,
                    "notes": r.notes,
                    "votes_up": r.votes_up,
                    "votes_down": r.votes_down,
                    "tested_by": r.tested_by,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reports
            ],
        }
    
    def get_alternatives(self, nexus_mod_id: int) -> List[Dict[str, Any]]:
        """Get alternative mods for a broken mod"""
        reports = self.db.query(ModCompatibilityReport).filter(
            ModCompatibilityReport.nexus_mod_id == nexus_mod_id
        ).all()
        
        alternatives = []
        for report in reports:
            for alt in report.alternatives:
                alternatives.append({
                    "mod_id": alt.alternative_nexus_mod_id,
                    "mod_name": alt.alternative_mod_name,
                    "mod_url": alt.alternative_mod_url,
                    "reason": alt.reason,
                    "similarity": alt.similarity_score,
                    "votes_up": alt.votes_up,
                    "votes_down": alt.votes_down,
                })
        
        # Sort by votes
        alternatives.sort(key=lambda x: x["votes_up"] - x["votes_down"], reverse=True)
        return alternatives
    
    def search_compatible_mods(
        self, 
        query: Optional[str] = None,
        status: Optional[CompatibilityStatus] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search for mods with known compatibility status"""
        q = self.db.query(ModCompatibilityReport)
        
        if query:
            q = q.filter(ModCompatibilityReport.mod_name.ilike(f"%{query}%"))
        
        if status:
            q = q.filter(ModCompatibilityReport.status == status)
        
        # Get distinct mods with their best report
        reports = q.order_by(
            ModCompatibilityReport.votes_up.desc()
        ).limit(limit).all()
        
        # Aggregate by mod
        mods = {}
        for report in reports:
            mod_id = report.nexus_mod_id
            if mod_id not in mods:
                mods[mod_id] = {
                    "nexus_mod_id": mod_id,
                    "mod_name": report.mod_name,
                    "status": report.status.value,
                    "port_url": report.macos_port_url,
                    "total_reports": 1,
                    "total_votes": report.votes_up + report.votes_down,
                }
            else:
                mods[mod_id]["total_reports"] += 1
                mods[mod_id]["total_votes"] += report.votes_up + report.votes_down
        
        return list(mods.values())
    
    def get_known_macos_mods(self) -> List[Dict[str, Any]]:
        """Get list of known macOS-compatible mods"""
        mods = self.db.query(KnownMacOSMod).filter(
            KnownMacOSMod.is_verified == True
        ).all()
        
        return [
            {
                "id": m.id,
                "name": m.name,
                "nexus_mod_id": m.nexus_mod_id,
                "github_url": m.github_url,
                "download_url": m.download_url,
                "latest_version": m.latest_version,
                "is_framework": m.is_framework,
                "description": m.description,
                "category": m.category,
            }
            for m in mods
        ]
    
    # ============================================================
    # Report Methods
    # ============================================================
    
    def create_report(
        self,
        nexus_mod_id: int,
        mod_name: str,
        status: CompatibilityStatus,
        tested_by: str = "anonymous",
        mod_version: Optional[str] = None,
        notes: Optional[str] = None,
        macos_port_url: Optional[str] = None,
        game_version: Optional[str] = None,
        red4ext_version: Optional[str] = None,
        macos_version: Optional[str] = None,
    ) -> ModCompatibilityReport:
        """Create a new compatibility report"""
        report = ModCompatibilityReport(
            nexus_mod_id=nexus_mod_id,
            mod_name=mod_name,
            mod_version=mod_version,
            status=status,
            macos_port_url=macos_port_url,
            tested_game_version=game_version,
            tested_red4ext_version=red4ext_version,
            tested_macos_version=macos_version,
            tested_by=tested_by,
            notes=notes,
        )
        
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        
        return report
    
    def vote_on_report(
        self,
        report_id: int,
        voter_id: str,
        is_upvote: bool
    ) -> bool:
        """Vote on a compatibility report"""
        # Check for existing vote
        existing = self.db.query(CompatibilityVote).filter(
            CompatibilityVote.report_id == report_id,
            CompatibilityVote.voter_id == voter_id
        ).first()
        
        if existing:
            # Already voted, update vote if different
            if existing.is_upvote != is_upvote:
                existing.is_upvote = is_upvote
                # Update report counts
                report = self.db.query(ModCompatibilityReport).get(report_id)
                if report:
                    if is_upvote:
                        report.votes_up += 1
                        report.votes_down -= 1
                    else:
                        report.votes_up -= 1
                        report.votes_down += 1
                self.db.commit()
            return True
        
        # Create new vote
        vote = CompatibilityVote(
            report_id=report_id,
            voter_id=voter_id,
            is_upvote=is_upvote
        )
        self.db.add(vote)
        
        # Update report counts
        report = self.db.query(ModCompatibilityReport).get(report_id)
        if report:
            if is_upvote:
                report.votes_up += 1
            else:
                report.votes_down += 1
        
        self.db.commit()
        return True
    
    def add_alternative(
        self,
        report_id: int,
        alternative_mod_id: int,
        alternative_mod_name: str,
        reason: Optional[str] = None,
        mod_url: Optional[str] = None,
        similarity: int = 50
    ) -> CompatibilityAlternative:
        """Add an alternative mod suggestion"""
        alt = CompatibilityAlternative(
            broken_mod_report_id=report_id,
            alternative_nexus_mod_id=alternative_mod_id,
            alternative_mod_name=alternative_mod_name,
            alternative_mod_url=mod_url,
            reason=reason,
            similarity_score=similarity
        )
        
        self.db.add(alt)
        self.db.commit()
        self.db.refresh(alt)
        
        return alt
    
    # ============================================================
    # Admin Methods
    # ============================================================
    
    def add_known_mod(
        self,
        name: str,
        nexus_mod_id: Optional[int] = None,
        github_url: Optional[str] = None,
        download_url: Optional[str] = None,
        is_framework: bool = False,
        description: Optional[str] = None,
        category: Optional[str] = None
    ) -> KnownMacOSMod:
        """Add a known macOS-compatible mod"""
        mod = KnownMacOSMod(
            name=name,
            nexus_mod_id=nexus_mod_id,
            github_url=github_url,
            download_url=download_url,
            is_framework=is_framework,
            is_verified=True,
            description=description,
            category=category
        )
        
        self.db.add(mod)
        self.db.commit()
        self.db.refresh(mod)
        
        return mod
    
    def get_stats(self) -> Dict[str, Any]:
        """Get compatibility database statistics"""
        total_reports = self.db.query(func.count(ModCompatibilityReport.id)).scalar()
        total_mods = self.db.query(func.count(func.distinct(ModCompatibilityReport.nexus_mod_id))).scalar()
        total_known = self.db.query(func.count(KnownMacOSMod.id)).scalar()
        
        by_status = {}
        status_counts = self.db.query(
            ModCompatibilityReport.status,
            func.count(ModCompatibilityReport.id)
        ).group_by(ModCompatibilityReport.status).all()
        
        for status, count in status_counts:
            by_status[status.value] = count
        
        return {
            "total_reports": total_reports or 0,
            "unique_mods": total_mods or 0,
            "known_compatible": total_known or 0,
            "by_status": by_status,
        }
