#!/usr/bin/env python3
"""Run the mod manager application"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        reload_includes=["*.py", "*.html"],
        reload_excludes=["*.pyc", "__pycache__", "*.db"]
    )
