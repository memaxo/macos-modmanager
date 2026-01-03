"""
Process Monitoring Service

Provides process monitoring capabilities using psutil for tracking
game process metrics, status, and lifecycle.
"""

import psutil
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum


class ProcessStatus(str, Enum):
    """Process status states"""
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    UNKNOWN = "unknown"


class ProcessMonitor:
    """Monitors a process by PID"""
    
    def __init__(self, pid: int):
        self.pid = pid
        self._start_time: Optional[datetime] = None
        self._last_check: Optional[datetime] = None
        
    def get_status(self) -> ProcessStatus:
        """Get current process status"""
        try:
            process = psutil.Process(self.pid)
            if process.is_running():
                return ProcessStatus.RUNNING
            else:
                return ProcessStatus.STOPPED
        except psutil.NoSuchProcess:
            return ProcessStatus.STOPPED
        except psutil.AccessDenied:
            return ProcessStatus.UNKNOWN
        except Exception:
            return ProcessStatus.UNKNOWN
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current process metrics"""
        try:
            process = psutil.Process(self.pid)
            
            # Get CPU and memory
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Get system memory for percentage
            system_memory = psutil.virtual_memory()
            memory_percent = (memory_info.rss / system_memory.total) * 100
            
            # Calculate uptime
            try:
                create_time = datetime.fromtimestamp(process.create_time())
                uptime_seconds = int((datetime.now() - create_time).total_seconds())
            except Exception:
                uptime_seconds = 0
            
            status = self.get_status()
            
            return {
                "status": status.value,
                "pid": self.pid,
                "uptime_seconds": uptime_seconds,
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_mb, 2),
                "memory_percent": round(memory_percent, 2),
                "is_running": status == ProcessStatus.RUNNING
            }
        except psutil.NoSuchProcess:
            return {
                "status": ProcessStatus.STOPPED.value,
                "pid": self.pid,
                "uptime_seconds": 0,
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "memory_percent": 0.0,
                "is_running": False
            }
        except psutil.AccessDenied:
            return {
                "status": ProcessStatus.UNKNOWN.value,
                "pid": self.pid,
                "uptime_seconds": 0,
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "memory_percent": 0.0,
                "is_running": False
            }
        except Exception as e:
            return {
                "status": ProcessStatus.UNKNOWN.value,
                "pid": self.pid,
                "uptime_seconds": 0,
                "cpu_percent": 0.0,
                "memory_mb": 0.0,
                "memory_percent": 0.0,
                "is_running": False,
                "error": str(e)
            }
    
    def is_running(self) -> bool:
        """Check if process is still running"""
        return self.get_status() == ProcessStatus.RUNNING
    
    def get_process(self) -> Optional[psutil.Process]:
        """Get psutil Process object"""
        try:
            return psutil.Process(self.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
    
    def terminate(self) -> bool:
        """Gracefully terminate the process"""
        try:
            process = psutil.Process(self.pid)
            process.terminate()
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    def kill(self) -> bool:
        """Force kill the process"""
        try:
            process = psutil.Process(self.pid)
            process.kill()
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    def set_priority(self, nice: int) -> bool:
        """Set process priority (nice level)"""
        try:
            process = psutil.Process(self.pid)
            process.nice(nice)
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            return False


def find_process_by_name(name: str) -> Optional[ProcessMonitor]:
    """Find a process by name and return ProcessMonitor"""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if name.lower() in proc.info['name'].lower():
                return ProcessMonitor(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None
