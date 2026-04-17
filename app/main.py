import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine, get_db
from app.models import AdminState, FactorType, RouteFactor
from app.schemas import (
    AppliedFactor,
    FactorIn,
    FactorOut,
    GraphResponse,
    PathResponse,
    PathStep,
    RouteContext,
    StationOut,
    WeatherIn,
    WeatherOut,
)
from app.services.metro import enrich_database, get_shortest_path
from app.services.weather import weather_refresh_loop

logger = logging.getLogger(__name__)


# Weekday bitmasks (Mon=bit0, ..., Sun=bit6)
WEEKDAYS_MON_FRI = 0b0011111  # 31
WEEKDAYS_SAT_SUN = 0b1100000  # 96


DEFAULT_FACTORS: list[dict] = [
    # Rush hour — общий для всех линий, будни
    {"name": "Утренний час пик", "factor_type": FactorType.rush_hour, "multiplier": 1.25,
     "applies_to_segment": True, "applies_to_transfer": True,
     "hour_start": 7, "hour_end": 10, "weekday_mask": WEEKDAYS_MON_FRI},
    {"name": "Вечерний час пик", "factor_type": FactorType.rush_hour, "multiplier": 1.30,
     "applies_to_segment": True, "applies_to_transfer": True,
     "hour_start": 17, "hour_end": 20, "weekday_mask": WEEKDAYS_MON_FRI},

    # Фиолетовая (line 7) — самая загруженная в час пик
    {"name": "Фиолетовая — утренний пик", "factor_type": FactorType.line, "multiplier": 1.20,
     "applies_to_segment": True, "applies_to_transfer": False,
     "line_id": "7", "hour_start": 7, "hour_end": 10, "weekday_mask": WEEKDAYS_MON_FRI},
    {"name": "Фиолетовая — вечерний пик", "factor_type": FactorType.line, "multiplier": 1.20,
     "applies_to_segment": True, "applies_to_transfer": False,
     "line_id": "7", "hour_start": 17, "hour_end": 20, "weekday_mask": WEEKDAYS_MON_FRI},

    # Серая (line 9) — перегруженность в час пик
    {"name": "Серая — утренний пик", "factor_type": FactorType.line, "multiplier": 1.15,
     "applies_to_segment": True, "applies_to_transfer": False,
     "line_id": "9", "hour_start": 7, "hour_end": 10, "weekday_mask": WEEKDAYS_MON_FRI},
    {"name": "Серая — вечерний пик", "factor_type": FactorType.line, "multiplier": 1.15,
     "applies_to_segment": True, "applies_to_transfer": False,
     "line_id": "9", "hour_start": 17, "hour_end": 20, "weekday_mask": WEEKDAYS_MON_FRI},

    # Оранжевая (line 6) — перегруженность в час пик
    {"name": "Оранжевая — утренний пик", "factor_type": FactorType.line, "multiplier": 1.10,
     "applies_to_segment": True, "applies_to_transfer": False,
     "line_id": "6", "hour_start": 7, "hour_end": 10, "weekday_mask": WEEKDAYS_MON_FRI},
    {"name": "Оранжевая — вечерний пик", "factor_type": FactorType.line, "multiplier": 1.10,
     "applies_to_segment": True, "applies_to_transfer": False,
     "line_id": "6", "hour_start": 17, "hour_end": 20, "weekday_mask": WEEKDAYS_MON_FRI},

    # Кольцевая (line 5) — длинные пешие пересадки; применяется к transfer всегда
    {"name": "Кольцевая — длинные переходы", "factor_type": FactorType.line, "multiplier": 1.25,
     "applies_to_segment": False, "applies_to_transfer": True, "line_id": "5"},

    # Выходные — увеличенные интервалы
    {"name": "Выходные — интервалы", "factor_type": FactorType.weekend, "multiplier": 1.15,
     "applies_to_segment": True, "applies_to_transfer": False,
     "weekday_mask": WEEKDAYS_SAT_SUN},

    # Погода — удлиняет переходы
    {"name": "Дождь — переходы", "factor_type": FactorType.weather, "multiplier": 1.15,
     "applies_to_segment": False, "applies_to_transfer": True, "weather_condition": "rain"},
    {"name": "Снег — переходы", "factor_type": FactorType.weather, "multiplier": 1.25,
     "applies_to_segment": False, "applies_to_transfer": True, "weather_condition": "snow"},
]


async def seed_default_factors(session: AsyncSession) -> None:
    """Insert default factors only if the table is empty (idempotent)."""
    res = await session.execute(select(RouteFactor.id).limit(1))
    if res.scalars().first() is not None:
        return
    for data in DEFAULT_FACTORS:
        session.add(RouteFactor(**data))
    # ensure singleton AdminState exists
    state_res = await session.execute(select(AdminState).where(AdminState.id == 1))
    if state_res.scalars().first() is None:
        session.add(AdminState(id=1, current_weather="clear"))
    await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        # Всегда пересобираем данные метро при старте,
        # чтобы применялись COORDINATE_FIXES и EDGE_* патчи.
        await enrich_database(session)
        await seed_default_factors(session)

    weather_stop: asyncio.Event | None = None
    weather_task: asyncio.Task | None = None
    if settings.openweather_api_key:
        weather_stop = asyncio.Event()
        weather_task = asyncio.create_task(weather_refresh_loop(weather_stop))
        logger.info(
            "OpenWeather refresh enabled, every %d min", settings.weather_refresh_minutes
        )
    else:
        logger.info("OpenWeather refresh disabled (OPENWEATHER_API_KEY is empty)")

    try:
        yield
    finally:
        if weather_task is not None and weather_stop is not None:
            weather_stop.set()
            try:
                await asyncio.wait_for(weather_task, timeout=5.0)
            except asyncio.TimeoutError:
                weather_task.cancel()
        await engine.dispose()


app = FastAPI(title="Московское метро — кратчайший путь", lifespan=lifespan)


def require_admin(x_api_key: str = Header(alias="X-API-Key", default="")) -> None:
    if not settings.admin_api_key or x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/admin/refresh", dependencies=[Depends(require_admin)])
async def refresh_metro(db: AsyncSession = Depends(get_db)):
    """Обновить данные из API HH и пересчитать переходы и поездки."""
    stations_count, trips_count = await enrich_database(db)
    return {"stations": stations_count, "trips": trips_count}


@app.get("/stations", response_model=list[StationOut])
async def list_stations(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, description="Поиск по названию"),
    limit: int = Query(100, ge=1, le=500),
):
    from app.models import Station
    q = select(Station).limit(limit * 2)
    if search:
        q = q.where(Station.name.ilike(f"%{search}%"))
    result = await db.execute(q)
    stations = result.scalars().unique().all()[:limit]
    return [
        StationOut(
            id=s.id,
            name=s.name,
            line_name=s.line_name,
            line_color=s.line_color,
        )
        for s in stations
    ]


@app.get("/path", response_model=PathResponse)
async def shortest_path(
    from_id: str = Query(..., description="ID станции отправления (например 1.148)"),
    to_id: str = Query(..., description="ID станции назначения"),
    override_time: datetime | None = Query(
        None, description="ISO datetime для симуляции времени (требует admin-ключ)"
    ),
    override_weather: str | None = Query(
        None, description="clear|rain|snow|fog для симуляции (требует admin-ключ)"
    ),
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(alias="X-API-Key", default=""),
):
    """Кратчайший путь с учётом динамических факторов."""
    is_admin = bool(settings.admin_api_key) and x_api_key == settings.admin_api_key
    eff_time = override_time if (override_time is not None and is_admin) else None
    eff_weather = override_weather if (override_weather is not None and is_admin) else None

    result = await get_shortest_path(db, from_id, to_id, now=eff_time, weather_override=eff_weather)
    if not result:
        raise HTTPException(status_code=404, detail="Путь не найден или неверные ID станций")
    path = result["path"]
    station_by_id = result["station_by_id"]
    breakdown = result["edge_breakdown"]

    steps: list[PathStep] = []
    for i, (sid, is_transfer) in enumerate(path):
        s = station_by_id[sid]
        if i == 0:
            steps.append(PathStep(
                station_id=s.id, station_name=s.name,
                line_name=s.line_name, is_transfer=is_transfer,
            ))
        else:
            b = breakdown[i - 1]
            steps.append(PathStep(
                station_id=s.id, station_name=s.name,
                line_name=s.line_name, is_transfer=is_transfer,
                base_minutes=round(b["base"], 3),
                multiplier=round(b["multiplier"], 4),
                final_minutes=round(b["final"], 3),
                factors_applied=list(b["factors"]),
            ))

    # Summary: aggregate applied factors across segments
    summary_map: dict[str, dict] = {}
    # We need factor metadata (type, multiplier) — reload active factors quickly
    factors_res = await db.execute(
        select(RouteFactor).where(RouteFactor.is_active == True)  # noqa: E712
    )
    factor_meta = {f.name: (f.factor_type, float(f.multiplier)) for f in factors_res.scalars().all()}

    for seg in breakdown:
        for name in seg["factors"]:
            entry = summary_map.get(name)
            if entry is None:
                meta = factor_meta.get(name)
                if meta is None:
                    continue
                summary_map[name] = {
                    "name": name,
                    "type": meta[0],
                    "multiplier": meta[1],
                    "segments_affected": 1,
                }
            else:
                entry["segments_affected"] += 1

    applied_summary = [AppliedFactor(**v) for v in summary_map.values()]

    ctx = result["context"]
    return PathResponse(
        from_station=StationOut(
            id=result["from_station"].id,
            name=result["from_station"].name,
            line_name=result["from_station"].line_name,
            line_color=result["from_station"].line_color,
        ),
        to_station=StationOut(
            id=result["to_station"].id,
            name=result["to_station"].name,
            line_name=result["to_station"].line_name,
            line_color=result["to_station"].line_color,
        ),
        path=steps,
        total_steps=len(steps) - 1,
        stations_count=len(steps),
        transfers_count=sum(1 for s in steps if s.is_transfer),
        total_time_minutes=round(result["total_minutes"], 2),
        base_total_minutes=round(result["base_total_minutes"], 2),
        applied_factors_summary=applied_summary,
        context=RouteContext(
            evaluated_at=ctx["evaluated_at"],
            weekday=ctx["weekday"],
            hour=ctx["hour"],
            weather=ctx["weather"],
        ),
    )


# ----- Factors: public read, admin write -----

@app.get("/factors", response_model=list[FactorOut])
async def list_factors_public(db: AsyncSession = Depends(get_db)):
    """Список действующих коэффициентов времени (открытый, без auth)."""
    res = await db.execute(select(RouteFactor).order_by(RouteFactor.id))
    return list(res.scalars().all())


@app.get("/admin/factors", response_model=list[FactorOut], dependencies=[Depends(require_admin)])
async def list_factors(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(RouteFactor).order_by(RouteFactor.id))
    return list(res.scalars().all())


@app.post("/admin/factors", response_model=FactorOut, status_code=201,
          dependencies=[Depends(require_admin)])
async def create_factor(payload: FactorIn, db: AsyncSession = Depends(get_db)):
    row = RouteFactor(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@app.put("/admin/factors/{factor_id}", response_model=FactorOut,
         dependencies=[Depends(require_admin)])
async def update_factor(factor_id: int, payload: FactorIn, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(RouteFactor).where(RouteFactor.id == factor_id))
    row = res.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Factor not found")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


@app.delete("/admin/factors/{factor_id}", status_code=204,
            dependencies=[Depends(require_admin)])
async def delete_factor(factor_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(RouteFactor).where(RouteFactor.id == factor_id))
    row = res.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Factor not found")
    await db.delete(row)
    await db.commit()


# ----- Weather: public read, admin write -----

def _weather_out(row: AdminState | None) -> WeatherOut:
    if row is None:
        return WeatherOut(condition="clear", source="manual")
    return WeatherOut(
        condition=row.current_weather,
        source=row.weather_source,
        updated_at=row.updated_at,
    )


@app.get("/weather", response_model=WeatherOut)
async def get_weather_public(db: AsyncSession = Depends(get_db)):
    """Текущее погодное условие (публичный, без auth)."""
    res = await db.execute(select(AdminState).where(AdminState.id == 1))
    return _weather_out(res.scalars().first())


@app.get("/admin/weather", response_model=WeatherOut, dependencies=[Depends(require_admin)])
async def get_weather(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AdminState).where(AdminState.id == 1))
    return _weather_out(res.scalars().first())


@app.put("/admin/weather", response_model=WeatherOut, dependencies=[Depends(require_admin)])
async def set_weather(payload: WeatherIn, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AdminState).where(AdminState.id == 1))
    row = res.scalars().first()
    if row is None:
        row = AdminState(id=1, current_weather=payload.condition, weather_source="manual")
        db.add(row)
    else:
        row.current_weather = payload.condition
        row.weather_source = "manual"
    await db.commit()
    await db.refresh(row)
    return _weather_out(row)


# Станции, которые не показываем на графе (по id)
HIDDEN_STATION_IDS = {
    "97.603",   # Деловой центр (БКЛ)
    "97.602",   # Шелепиха (БКЛ)
    "136.896",  # Ермакова Роща (МЦД-4)
}


@app.get("/graph", response_model=GraphResponse)
async def full_graph(db: AsyncSession = Depends(get_db)):
    """Полный граф метро: все станции и рёбра между ними."""
    from app.models import Station, Trip, EdgeType

    stations_result = await db.execute(select(Station))
    stations = stations_result.scalars().unique().all()

    stations_filtered = [
        s for s in stations
        if s.id not in HIDDEN_STATION_IDS
    ]
    allowed_ids = {s.id for s in stations_filtered}

    trips_result = await db.execute(select(Trip))
    trips = trips_result.scalars().unique().all()

    stations_out = [
        {
            "id": s.id,
            "name": s.name,
            "line_id": s.line_id,
            "line_name": s.line_name,
            "line_color": s.line_color,
            "lat": s.lat,
            "lng": s.lng,
        }
        for s in stations_filtered
    ]
    edges_out = [
        {
            "from_id": t.from_station_id,
            "to_id": t.to_station_id,
            "is_transfer": t.edge_type == EdgeType.transfer,
        }
        for t in trips
        if t.from_station_id in allowed_ids and t.to_station_id in allowed_ids
    ]
    return GraphResponse(stations=stations_out, edges=edges_out)
