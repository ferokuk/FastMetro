from pydantic import BaseModel
from typing import List, Optional


class StationOut(BaseModel):
    id: str
    name: str
    line_name: str

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
    total_time_minutes: float  # общее время в пути, мин
