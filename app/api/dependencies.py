from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.mod import Mod, ModDependency
from app.core.dependency_resolver import DependencyResolver
from typing import List

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/tree", response_class=HTMLResponse)
async def get_dependency_tree(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get dependency tree as HTML"""
    resolver = DependencyResolver(db)
    
    # Get all mods with dependencies
    mods_result = await db.execute(select(Mod).where(Mod.is_active == True))
    mods = mods_result.scalars().all()
    
    # Build dependency tree
    tree_data = []
    for mod in mods:
        deps_result = await db.execute(
            select(ModDependency).where(ModDependency.mod_id == mod.id)
        )
        dependencies = deps_result.scalars().all()
        
        if dependencies:
            tree_data.append({
                "mod": mod,
                "dependencies": dependencies
            })
    
    return templates.TemplateResponse("components/dependency_tree.html", {
        "request": request,
        "tree_data": tree_data
    })


@router.post("/install/{dependency_name}")
async def install_dependency(
    dependency_name: str,
    db: AsyncSession = Depends(get_db)
):
    """Install a missing dependency"""
    # TODO: Implement dependency installation
    return {"message": f"Dependency {dependency_name} installation not yet implemented"}
