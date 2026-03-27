from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from ..database import Base


class Area(Base):
    __tablename__ = "areas"

    id = Column(Integer, primary_key=True)
    boolder_id = Column(Integer, unique=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(200), unique=True, index=True)

    # Geography
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    geom = Column(Geometry("POINT", srid=4326), index=True)
    elevation_m = Column(Integer)
    bbox_sw_lon = Column(Float, nullable=True)
    bbox_sw_lat = Column(Float, nullable=True)
    bbox_ne_lon = Column(Float, nullable=True)
    bbox_ne_lat = Column(Float, nullable=True)

    # Physical characteristics (affect drying rate)
    # Aspect: cardinal direction the rock faces — affects solar exposure
    aspect = Column(String(20))  # 'N','NE','E','SE','S','SW','W','NW','flat'
    # 0 = complete shade, 1 = full sun
    shade_factor = Column(Float, default=0.5)
    # 0 = no canopy (open), 1 = dense canopy (sheltered)
    canopy_factor = Column(Float, default=0.5)
    rock_type = Column(String(50), default="sandstone")

    description = Column(Text)
    osm_tags = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    boulders = relationship("Boulder", back_populates="area", lazy="select")
    weather_readings = relationship("WeatherReading", back_populates="area", lazy="select")
    dryness_scores = relationship(
        "DrynessScore",
        primaryjoin="and_(DrynessScore.area_id == Area.id, DrynessScore.boulder_id == None)",
        foreign_keys="DrynessScore.area_id",
        lazy="select",
    )
