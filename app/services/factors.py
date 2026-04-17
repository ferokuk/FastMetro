from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

from app.models import FactorType, RouteFactor


@dataclass(frozen=True)
class EdgeContext:
    line_id: str           # source line; for segments == destination line
    is_transfer: bool
    other_line_id: str | None = None  # destination line for transfers; None for segments

    def involves_line(self, line_id: str) -> bool:
        if self.line_id == line_id:
            return True
        if self.other_line_id is not None and self.other_line_id == line_id:
            return True
        return False


@dataclass(frozen=True)
class QueryContext:
    now: datetime
    weather: str


def _weekday_matches(mask: int | None, weekday: int) -> bool:
    if mask is None:
        return True
    return bool(mask & (1 << weekday))


def _hour_matches(hour_start: int | None, hour_end: int | None, hour: int) -> bool:
    if hour_start is None or hour_end is None:
        return True
    return hour_start <= hour < hour_end


def match(factor: RouteFactor, edge: EdgeContext, qctx: QueryContext) -> bool:
    if not factor.is_active:
        return False
    if edge.is_transfer and not factor.applies_to_transfer:
        return False
    if (not edge.is_transfer) and not factor.applies_to_segment:
        return False

    weekday = qctx.now.weekday()
    hour = qctx.now.hour

    ftype = factor.factor_type
    if ftype == FactorType.rush_hour:
        if not _hour_matches(factor.hour_start, factor.hour_end, hour):
            return False
        if not _weekday_matches(factor.weekday_mask, weekday):
            return False
        return True

    if ftype == FactorType.weekend:
        return _weekday_matches(factor.weekday_mask, weekday)

    if ftype == FactorType.line:
        if factor.line_id is None or not edge.involves_line(factor.line_id):
            return False
        if not _weekday_matches(factor.weekday_mask, weekday):
            return False
        if not _hour_matches(factor.hour_start, factor.hour_end, hour):
            return False
        return True

    if ftype == FactorType.weather:
        if factor.weather_condition is None:
            return False
        return qctx.weather == factor.weather_condition

    return False


def compute_edge_minutes(
    base: float,
    edge: EdgeContext,
    qctx: QueryContext,
    factors: List[RouteFactor],
) -> Tuple[float, float, List[RouteFactor]]:
    """Compute per-edge time with multiplicative factor combination.

    Returns (base, final, applied_factors).
    """
    applied: List[RouteFactor] = []
    multiplier = 1.0
    for f in factors:
        if match(f, edge, qctx):
            multiplier *= float(f.multiplier)
            applied.append(f)
    return base, base * multiplier, applied
