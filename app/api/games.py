from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.game_detector import detect_cyberpunk_installations
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()


class GameResponse(BaseModel):
    path: str
    launcher: str
    version: Optional[str]


@router.get("/")
async def list_games(db: AsyncSession = Depends(get_db)) -> List[GameResponse]:
    """List detected Cyberpunk 2077 installations"""
    installations = await detect_cyberpunk_installations()
    return [
        GameResponse(
            path=inst["path"],
            launcher=inst["launcher"],
            version=inst.get("version")
        )
        for inst in installations
    ]


@router.post("/detect")
async def detect_games(db: AsyncSession = Depends(get_db)) -> List[GameResponse]:
    """Force detection of game installations"""
    installations = await detect_cyberpunk_installations()
    return [
        GameResponse(
            path=inst["path"],
            launcher=inst["launcher"],
            version=inst.get("version")
        )
        for inst in installations
    ]
