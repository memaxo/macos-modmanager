"""
Launch Logger Service

In-memory log storage for launch sessions. Stores launch logs
during the session and provides filtering/search capabilities.
"""

from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from collections import deque
from enum import Enum
import uuid


class LogLevel(str, Enum):
    """Log severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


class LaunchPhase(str, Enum):
    """Launch phases"""
    PRE_LAUNCH = "pre-launch"
    LAUNCHING = "launching"
    RUNNING = "running"
    STOPPED = "stopped"


class LogSource(str, Enum):
    """Log sources"""
    LAUNCHER = "launcher"
    RED4EXT = "red4ext"
    TWEAKXL = "tweakxl"
    ARCHIVEXL = "archivexl"
    REDSCRIPT = "redscript"
    GAME = "game"
    UNKNOWN = "unknown"


class LaunchLogger:
    """Singleton class for storing launch logs in memory"""
    
    _instance: Optional['LaunchLogger'] = None
    MAX_SESSIONS = 10
    MAX_LOG_LINES_PER_SESSION = 10000
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._current_session_id: Optional[str] = None
        self._initialized = True
    
    def start_session(self) -> str:
        """Start a new launch session"""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "id": session_id,
            "started_at": datetime.now(),
            "logs": deque(maxlen=self.MAX_LOG_LINES_PER_SESSION),
            "phase": LaunchPhase.PRE_LAUNCH.value,
            "status": "starting"
        }
        self._current_session_id = session_id
        
        # Cleanup old sessions
        self._cleanup_old_sessions()
        
        return session_id
    
    def get_current_session_id(self) -> Optional[str]:
        """Get current active session ID"""
        return self._current_session_id
    
    def log(
        self,
        message: str,
        level: LogLevel = LogLevel.INFO,
        source: LogSource = LogSource.LAUNCHER,
        phase: Optional[LaunchPhase] = None,
        session_id: Optional[str] = None
    ):
        """Add a log entry"""
        if session_id is None:
            session_id = self._current_session_id
        
        if session_id is None:
            # Auto-start session if none exists
            session_id = self.start_session()
        
        if session_id not in self._sessions:
            return
        
        log_entry = {
            "timestamp": datetime.now(),
            "level": level.value,
            "phase": phase.value if phase else self._sessions[session_id]["phase"],
            "message": message,
            "source": source.value
        }
        
        self._sessions[session_id]["logs"].append(log_entry)
        
        # Update phase if provided
        if phase:
            self._sessions[session_id]["phase"] = phase.value
    
    def update_session_status(self, status: str, session_id: Optional[str] = None):
        """Update session status"""
        if session_id is None:
            session_id = self._current_session_id
        
        if session_id and session_id in self._sessions:
            self._sessions[session_id]["status"] = status
    
    def get_logs(
        self,
        session_id: Optional[str] = None,
        level_filter: Optional[Set[LogLevel]] = None,
        source_filter: Optional[Set[LogSource]] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get logs with optional filtering"""
        if session_id is None:
            session_id = self._current_session_id
        
        if session_id is None or session_id not in self._sessions:
            return []
        
        logs = list(self._sessions[session_id]["logs"])
        
        # Apply filters
        filtered_logs = []
        for log in logs:
            # Level filter
            if level_filter and LogLevel(log["level"]) not in level_filter:
                continue
            
            # Source filter
            if source_filter and LogSource(log["source"]) not in source_filter:
                continue
            
            # Search filter
            if search and search.lower() not in log["message"].lower():
                continue
            
            # Convert datetime to ISO format for JSON
            log_copy = log.copy()
            log_copy["timestamp"] = log["timestamp"].isoformat()
            filtered_logs.append(log_copy)
        
        # Apply limit
        if limit:
            filtered_logs = filtered_logs[-limit:]
        
        return filtered_logs
    
    def get_session_info(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get session information"""
        if session_id is None:
            session_id = self._current_session_id
        
        if session_id is None or session_id not in self._sessions:
            return None
        
        session = self._sessions[session_id]
        return {
            "id": session["id"],
            "started_at": session["started_at"].isoformat(),
            "phase": session["phase"],
            "status": session["status"],
            "log_count": len(session["logs"])
        }
    
    def _cleanup_old_sessions(self):
        """Remove old sessions, keeping only the most recent N"""
        if len(self._sessions) <= self.MAX_SESSIONS:
            return
        
        # Sort by start time, keep most recent
        sorted_sessions = sorted(
            self._sessions.items(),
            key=lambda x: x[1]["started_at"],
            reverse=True
        )
        
        # Remove old sessions
        for session_id, _ in sorted_sessions[self.MAX_SESSIONS:]:
            del self._sessions[session_id]
    
    def clear_session(self, session_id: Optional[str] = None):
        """Clear logs for a session"""
        if session_id is None:
            session_id = self._current_session_id
        
        if session_id and session_id in self._sessions:
            self._sessions[session_id]["logs"].clear()
    
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get info for all sessions"""
        return [
            {
                "id": session["id"],
                "started_at": session["started_at"].isoformat(),
                "phase": session["phase"],
                "status": session["status"],
                "log_count": len(session["logs"])
            }
            for session in self._sessions.values()
        ]


# Singleton instance
_launch_logger: Optional[LaunchLogger] = None


def get_launch_logger() -> LaunchLogger:
    """Get the singleton LaunchLogger instance"""
    global _launch_logger
    if _launch_logger is None:
        _launch_logger = LaunchLogger()
    return _launch_logger
