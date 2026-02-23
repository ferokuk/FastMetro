from sqlalchemy import Column, String, Float, Integer, ForeignKey, Enum
from app.database import Base
import enum


class EdgeType(str, enum.Enum):
    same_line = "same_line"
    transfer = "transfer"


class Station(Base):
    __tablename__ = "stations"

    id = Column(String(32), primary_key=True)  # e.g. "1.148", "8.189"
    name = Column(String(255), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    line_id = Column(String(16), nullable=False)
    line_name = Column(String(128), nullable=False)
    order = Column(Integer, nullable=False)


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_station_id = Column(String(32), ForeignKey("stations.id"), nullable=False)
    to_station_id = Column(String(32), ForeignKey("stations.id"), nullable=False)
    edge_type = Column(Enum(EdgeType), nullable=False)  # same_line or transfer
