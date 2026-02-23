from pydantic import BaseModel
from typing import List, Optional


class StationOut(BaseModel):
    id: str
    name: str
    line_name: str
    line_color: str

    class Config:
        from_attributes = True


class PathStep(BaseModel):
    station_id: str
    station_name: str
    line_name: str
    is_transfer: bool = False


class PathResponse(BaseModel):
    """Кратчайший путь по времени в пути (мок: 3 мин перегон, 6 мин переход)."""

    from_station: StationOut
    to_station: StationOut
    path: List[PathStep]
    total_steps: int  # число перегонов (рёбер)
    stations_count: int  # число станций в пути (включая начальную и конечную)
    transfers_count: int  # число пересадок
    total_time_minutes: float  # общее время в пути, мин


class GraphStationOut(BaseModel):
    id: str
    name: str
    line_id: str
    line_name: str
    line_color: str
    lat: float
    lng: float


class GraphEdgeOut(BaseModel):
    from_id: str
    to_id: str
    is_transfer: bool


class GraphResponse(BaseModel):
    """Полный граф метро: станции и рёбра между ними."""

    stations: List[GraphStationOut]
    edges: List[GraphEdgeOut]
