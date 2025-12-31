from sqlalchemy import Column, Integer, String, ForeignKey
from app.database import Base


class ModLoadOrder(Base):
    __tablename__ = "mod_load_order"
    
    id = Column(Integer, primary_key=True, index=True)
    mod_id = Column(Integer, ForeignKey("mods.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(String, nullable=False, index=True)
    profile_id = Column(Integer, ForeignKey("mod_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    priority = Column(Integer, nullable=False, index=True)
