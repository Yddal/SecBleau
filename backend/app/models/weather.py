from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class WeatherReading(Base):
    """Hourly weather data per area. One API call to Open-Meteo covers the whole sector."""
    __tablename__ = "weather_readings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False, index=True)

    # Source: 'open_meteo' or 'netatmo'
    source = Column(String(20), nullable=False, default="open_meteo")
    recorded_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Core weather variables used in evaporation model
    temperature_c = Column(Float)        # Air temp at 2m
    humidity_pct = Column(Float)         # Relative humidity 0-100
    precipitation_mm = Column(Float)     # Hourly precipitation
    wind_speed_ms = Column(Float)        # Wind speed at 10m (m/s)
    wind_direction_deg = Column(Integer) # Wind direction 0-360
    solar_radiation_wm2 = Column(Float)  # Shortwave radiation W/m²
    soil_moisture_m3 = Column(Float)     # Volumetric soil moisture 0-1

    # Full raw API response for reprocessing if model changes
    raw_response = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    area = relationship("Area", back_populates="weather_readings")

    __table_args__ = (
        Index("ix_weather_area_time", "area_id", "recorded_at"),
    )
