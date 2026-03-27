from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from ..database import Base


class Boulder(Base):
    __tablename__ = "boulders"

    id = Column(Integer, primary_key=True)
    boolder_problem_id = Column(Integer, unique=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False, index=True)

    name = Column(String(300))
    grade = Column(String(10))  # e.g. "6a", "7b+"

    # Geography
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    geom = Column(Geometry("POINT", srid=4326), index=True)

    # Physical characteristics — inherit from area if null
    # Null means "use area defaults"
    aspect = Column(String(20))
    shade_factor = Column(Float)   # None = inherit from area
    canopy_factor = Column(Float)  # None = inherit from area

    # Whether this boulder has enough direct reports to be fully opaque on map
    has_direct_data = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    area = relationship("Area", back_populates="boulders")
    reports = relationship("UserReport", back_populates="boulder", lazy="select")
    dryness_scores = relationship("DrynessScore", back_populates="boulder", lazy="select")
