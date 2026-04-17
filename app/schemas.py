from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional

from app.models import FactorType


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
    base_minutes: Optional[float] = None
    multiplier: Optional[float] = None
    final_minutes: Optional[float] = None
    factors_applied: List[str] = Field(default_factory=list)


class AppliedFactor(BaseModel):
    name: str
    type: FactorType
    multiplier: float
    segments_affected: int


class RouteContext(BaseModel):
    evaluated_at: datetime
    weekday: int  # 0=Mon..6=Sun
    hour: int
    weather: str


class PathResponse(BaseModel):
    """Кратчайший путь по времени в пути с учётом динамических факторов."""

    from_station: StationOut
    to_station: StationOut
    path: List[PathStep]
    total_steps: int  # число перегонов (рёбер)
    stations_count: int  # число станций в пути (включая начальную и конечную)
    transfers_count: int  # число пересадок
    total_time_minutes: float  # итоговое время с факторами, мин
    base_total_minutes: float  # базовое время без факторов, мин
    applied_factors_summary: List[AppliedFactor] = Field(default_factory=list)
    context: RouteContext


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


class FactorIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    factor_type: FactorType
    multiplier: float = Field(..., ge=1.0, le=2.0)
    applies_to_segment: bool = True
    applies_to_transfer: bool = False
    line_id: Optional[str] = Field(None, max_length=16)
    hour_start: Optional[int] = Field(None, ge=0, le=24)
    hour_end: Optional[int] = Field(None, ge=0, le=24)
    weekday_mask: Optional[int] = Field(None, ge=0, le=127)
    weather_condition: Optional[str] = Field(None, max_length=32)
    is_active: bool = True
    priority: int = 0

    @model_validator(mode="after")
    def _validate_hours(self):
        if (self.hour_start is None) != (self.hour_end is None):
            raise ValueError("hour_start and hour_end must be provided together")
        if self.hour_start is not None and self.hour_end is not None:
            if self.hour_start >= self.hour_end:
                raise ValueError("hour_start must be less than hour_end")
        return self

    @field_validator("weather_condition")
    @classmethod
    def _weather(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"clear", "rain", "snow", "fog"}
        if v not in allowed:
            raise ValueError(f"weather_condition must be one of {sorted(allowed)}")
        return v


class FactorOut(FactorIn):
    id: int

    class Config:
        from_attributes = True


class WeatherIn(BaseModel):
    condition: str

    @field_validator("condition")
    @classmethod
    def _valid(cls, v: str) -> str:
        allowed = {"clear", "rain", "snow", "fog"}
        if v not in allowed:
            raise ValueError(f"condition must be one of {sorted(allowed)}")
        return v


class WeatherOut(BaseModel):
    condition: str
    source: str = "manual"
    updated_at: Optional[datetime] = None
