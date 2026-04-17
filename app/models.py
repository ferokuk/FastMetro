from sqlalchemy import Boolean, Column, DateTime, String, Float, Integer, ForeignKey, Enum, func
from app.database import Base
import enum


class EdgeType(str, enum.Enum):
    same_line = "same_line"
    transfer = "transfer"


class FactorType(str, enum.Enum):
    rush_hour = "rush_hour"
    weekend = "weekend"
    line = "line"
    weather = "weather"


class Station(Base):
    __tablename__ = "stations"

    id = Column(String(32), primary_key=True)  # e.g. "1.148", "8.189"
    name = Column(String(255), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    line_id = Column(String(16), nullable=False)
    line_name = Column(String(128), nullable=False)
    line_color = Column(String(7), nullable=False, server_default="#888888")
    order = Column(Integer, nullable=False)


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_station_id = Column(String(32), ForeignKey("stations.id"), nullable=False)
    to_station_id = Column(String(32), ForeignKey("stations.id"), nullable=False)
    edge_type = Column(Enum(EdgeType), nullable=False)  # same_line or transfer


class RouteFactor(Base):
    __tablename__ = "route_factors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    factor_type = Column(Enum(FactorType), nullable=False)
    multiplier = Column(Float, nullable=False)
    applies_to_segment = Column(Boolean, nullable=False, default=True)
    applies_to_transfer = Column(Boolean, nullable=False, default=False)
    line_id = Column(String(16), nullable=True)
    hour_start = Column(Integer, nullable=True)
    hour_end = Column(Integer, nullable=True)
    weekday_mask = Column(Integer, nullable=True)  # Mon=1, Tue=2, ..., Sun=64; NULL = any day
    weather_condition = Column(String(32), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=0)


class AdminState(Base):
    __tablename__ = "admin_state"

    id = Column(Integer, primary_key=True, default=1)
    current_weather = Column(String(32), nullable=False, default="clear")
    weather_source = Column(String(16), nullable=False, default="manual")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
