"""
FOMOD Session Manager

Manages temporary sessions for FOMOD wizard installations.
Sessions track the extracted mod files, parsed configuration,
current step, and user choices throughout the wizard flow.
"""

import uuid
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List
import shutil
import asyncio

from app.core.fomod_parser import FomodConfig, FomodParser, FomodConditionFlag

logger = logging.getLogger(__name__)


@dataclass
class FomodSession:
    """Represents an active FOMOD installation wizard session"""
    session_id: str
    temp_dir: Path
    config: FomodConfig
    mod_info: Dict[str, Any]  # Basic mod info (nexus_mod_id, name, etc.)
    current_step: int = 0
    choices: Dict[str, Any] = field(default_factory=lambda: {"type": "fomod", "options": []})
    condition_flags: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=1))
    
    def is_expired(self) -> bool:
        """Check if this session has expired"""
        return datetime.now() > self.expires_at
    
    def extend_expiration(self, hours: int = 1):
        """Extend the session expiration time"""
        self.expires_at = datetime.now() + timedelta(hours=hours)
    
    def get_visible_steps(self) -> List[int]:
        """Get list of step indices that are currently visible"""
        visible = []
        for idx, step in enumerate(self.config.steps):
            if step.is_visible(self.condition_flags):
                visible.append(idx)
        return visible
    
    def get_current_step_data(self) -> Optional[Dict[str, Any]]:
        """Get the data for the current step"""
        visible_steps = self.get_visible_steps()
        if self.current_step >= len(visible_steps):
            return None
        
        step_idx = visible_steps[self.current_step]
        step = self.config.steps[step_idx]
        
        return {
            "step_index": self.current_step,
            "total_steps": len(visible_steps),
            "step_name": step.name,
            "groups": [g.to_dict() for g in step.groups],
            "is_first": self.current_step == 0,
            "is_last": self.current_step == len(visible_steps) - 1
        }
    
    def set_step_choices(self, step_idx: int, group_choices: List[Dict[str, Any]]):
        """Set choices for a specific step"""
        # Get the actual step
        visible_steps = self.get_visible_steps()
        if step_idx >= len(visible_steps):
            return
        
        actual_step_idx = visible_steps[step_idx]
        step = self.config.steps[actual_step_idx]
        
        # Ensure options list is long enough
        while len(self.choices["options"]) <= actual_step_idx:
            self.choices["options"].append({"name": "", "groups": []})
        
        # Set the choices
        self.choices["options"][actual_step_idx] = {
            "name": step.name,
            "groups": group_choices
        }
        
        # Update condition flags based on selected plugins
        for group_choice in group_choices:
            group_name = group_choice.get("name", "")
            
            # Find the matching group
            for group in step.groups:
                if group.name == group_name:
                    for choice in group_choice.get("choices", []):
                        plugin_idx = choice.get("idx", 0)
                        if plugin_idx < len(group.plugins):
                            plugin = group.plugins[plugin_idx]
                            # Set any condition flags from this plugin
                            for flag in plugin.condition_flags:
                                self.condition_flags[flag.name] = flag.value
    
    def can_advance(self) -> bool:
        """Check if we can advance to the next step"""
        visible_steps = self.get_visible_steps()
        return self.current_step < len(visible_steps) - 1
    
    def can_go_back(self) -> bool:
        """Check if we can go back to the previous step"""
        return self.current_step > 0
    
    def advance_step(self) -> bool:
        """Move to the next step if possible"""
        if self.can_advance():
            self.current_step += 1
            return True
        return False
    
    def go_back(self) -> bool:
        """Move to the previous step if possible"""
        if self.can_go_back():
            self.current_step -= 1
            return True
        return False
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all choices made"""
        summary = {
            "mod_name": self.mod_info.get("name", "Unknown Mod"),
            "steps": []
        }
        
        visible_steps = self.get_visible_steps()
        
        for vis_idx, step_idx in enumerate(visible_steps):
            step = self.config.steps[step_idx]
            step_summary = {
                "name": step.name,
                "groups": []
            }
            
            # Get choices for this step
            if step_idx < len(self.choices["options"]):
                step_choices = self.choices["options"][step_idx]
                for group_choice in step_choices.get("groups", []):
                    group_summary = {
                        "name": group_choice.get("name", ""),
                        "selections": []
                    }
                    for choice in group_choice.get("choices", []):
                        group_summary["selections"].append(choice.get("name", ""))
                    if group_summary["selections"]:
                        step_summary["groups"].append(group_summary)
            
            if step_summary["groups"]:
                summary["steps"].append(step_summary)
        
        return summary
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to a dictionary for API responses"""
        return {
            "session_id": self.session_id,
            "mod_info": self.mod_info,
            "config": self.config.to_dict(),
            "current_step": self.current_step,
            "choices": self.choices,
            "visible_steps": len(self.get_visible_steps()),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat()
        }


class FomodSessionManager:
    """Manages FOMOD wizard sessions"""
    
    _instance = None
    _sessions: Dict[str, FomodSession] = {}
    _cleanup_task: Optional[asyncio.Task] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._sessions = {}
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "FomodSessionManager":
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def create_session(
        self,
        config: FomodConfig,
        temp_dir: Path,
        mod_info: Dict[str, Any]
    ) -> str:
        """Create a new FOMOD wizard session
        
        Args:
            config: Parsed FOMOD configuration
            temp_dir: Path to extracted mod files
            mod_info: Dictionary with mod information (name, nexus_mod_id, etc.)
            
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        
        session = FomodSession(
            session_id=session_id,
            temp_dir=temp_dir,
            config=config,
            mod_info=mod_info
        )
        
        self._sessions[session_id] = session
        logger.info(f"Created FOMOD session {session_id} for mod: {mod_info.get('name', 'Unknown')}")
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[FomodSession]:
        """Get a session by ID
        
        Args:
            session_id: The session ID to look up
            
        Returns:
            FomodSession if found and not expired, None otherwise
        """
        session = self._sessions.get(session_id)
        
        if session is None:
            return None
        
        if session.is_expired():
            logger.info(f"Session {session_id} has expired, cleaning up")
            self._cleanup_session(session_id)
            return None
        
        # Extend expiration on access
        session.extend_expiration()
        
        return session
    
    def update_choices(
        self,
        session_id: str,
        step_idx: int,
        group_choices: List[Dict[str, Any]]
    ) -> bool:
        """Update choices for a step in a session
        
        Args:
            session_id: The session ID
            step_idx: The step index (0-based, of visible steps)
            group_choices: List of group choice dictionaries
            
        Returns:
            True if successful, False if session not found
        """
        session = self.get_session(session_id)
        if session is None:
            return False
        
        session.set_step_choices(step_idx, group_choices)
        return True
    
    def complete_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Complete a session and return the final choices
        
        Args:
            session_id: The session ID
            
        Returns:
            Dictionary with choices and temp_dir, or None if session not found
        """
        session = self.get_session(session_id)
        if session is None:
            return None
        
        result = {
            "choices": session.choices,
            "temp_dir": session.temp_dir,
            "config": session.config,
            "mod_info": session.mod_info
        }
        
        # Don't clean up temp_dir yet - let the installer handle it
        # Just remove from sessions
        del self._sessions[session_id]
        logger.info(f"Completed FOMOD session {session_id}")
        
        return result
    
    def cancel_session(self, session_id: str) -> bool:
        """Cancel a session and clean up resources
        
        Args:
            session_id: The session ID
            
        Returns:
            True if successful, False if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False
        
        self._cleanup_session(session_id)
        logger.info(f"Cancelled FOMOD session {session_id}")
        return True
    
    def _cleanup_session(self, session_id: str):
        """Clean up a session's resources"""
        session = self._sessions.get(session_id)
        if session is None:
            return
        
        # Clean up temp directory
        if session.temp_dir.exists():
            try:
                shutil.rmtree(session.temp_dir)
                logger.debug(f"Cleaned up temp dir for session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp dir for session {session_id}: {e}")
        
        del self._sessions[session_id]
    
    def cleanup_expired(self) -> int:
        """Clean up all expired sessions
        
        Returns:
            Number of sessions cleaned up
        """
        expired_ids = [
            sid for sid, session in self._sessions.items()
            if session.is_expired()
        ]
        
        for session_id in expired_ids:
            self._cleanup_session(session_id)
        
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired FOMOD sessions")
        
        return len(expired_ids)
    
    async def start_cleanup_task(self, interval_minutes: int = 15):
        """Start a background task to periodically clean up expired sessions"""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(interval_minutes * 60)
                self.cleanup_expired()
        
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(cleanup_loop())
            logger.info("Started FOMOD session cleanup task")
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get a list of all active sessions (for debugging)"""
        return [
            {
                "session_id": session.session_id,
                "mod_name": session.mod_info.get("name", "Unknown"),
                "current_step": session.current_step,
                "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat()
            }
            for session in self._sessions.values()
            if not session.is_expired()
        ]


# Exception raised when a FOMOD wizard is required
class FomodWizardRequired(Exception):
    """Raised when a mod requires FOMOD wizard interaction"""
    
    def __init__(self, session_id: str, config: FomodConfig, mod_info: Dict[str, Any]):
        self.session_id = session_id
        self.config = config
        self.mod_info = mod_info
        super().__init__(f"FOMOD wizard required for mod: {mod_info.get('name', 'Unknown')}")
