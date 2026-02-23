from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, engine, Base, AsyncSessionLocal
from app.schemas import PathResponse, PathStep, StationOut
from app.services.metro import enrich_database, get_shortest_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Optionally fill DB on startup (if empty)
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, func
        from app.models import Station
        r = await session.execute(select(func.count()).select_from(Station))
        if r.scalar() == 0:
            await enrich_database(session)
    yield
    await engine.dispose()


app = FastAPI(title="Московское метро — кратчайший путь", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/admin/refresh")
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
    from sqlalchemy import select
    from app.models import Station
    q = select(Station).limit(limit * 2)
    if search:
        q = q.where(Station.name.ilike(f"%{search}%"))
    result = await db.execute(q)
    stations = result.scalars().unique().all()[:limit]
    return [StationOut(id=s.id, name=s.name, line_name=s.line_name) for s in stations]


@app.get("/path", response_model=PathResponse)
async def shortest_path(
    from_id: str = Query(..., description="ID станции отправления (например 1.148)"),
    to_id: str = Query(..., description="ID станции назначения"),
    db: AsyncSession = Depends(get_db),
):
    """Кратчайший путь по времени в пути (3 мин — перегон, 6 мин — переход)."""
    result = await get_shortest_path(db, from_id, to_id)
    if not result:
        raise HTTPException(status_code=404, detail="Путь не найден или неверные ID станций")
    path = result["path"]
    station_by_id = result["station_by_id"]
    steps = []
    for i, (sid, is_transfer) in enumerate(path):
        s = station_by_id[sid]
        steps.append(
            PathStep(
                station_id=s.id,
                station_name=s.name,
                line_name=s.line_name,
                is_transfer=is_transfer,
            )
        )
    return PathResponse(
        from_station=StationOut(
            id=result["from_station"].id,
            name=result["from_station"].name,
            line_name=result["from_station"].line_name,
        ),
        to_station=StationOut(
            id=result["to_station"].id,
            name=result["to_station"].name,
            line_name=result["to_station"].line_name,
        ),
        path=steps,
        total_steps=len(steps) - 1,
        stations_count=len(steps),
        total_time_minutes=result["total_minutes"],
    )
