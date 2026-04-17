import asyncio
import logging
from typing import Optional

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import AdminState

logger = logging.getLogger(__name__)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

# Mapping от OpenWeather `weather[0].main` к нашим условиям.
CONDITION_MAP: dict[str, str] = {
    "Clear": "clear",
    "Clouds": "clear",
    "Rain": "rain",
    "Drizzle": "rain",
    "Thunderstorm": "rain",
    "Snow": "snow",
    "Mist": "fog",
    "Fog": "fog",
    "Haze": "fog",
    "Smoke": "fog",
    "Dust": "fog",
    "Sand": "fog",
    "Ash": "fog",
    "Squall": "rain",
    "Tornado": "rain",
}


async def fetch_openweather_condition() -> Optional[str]:
    """Fetch current weather for configured coords. Returns one of our condition codes or None."""
    if not settings.openweather_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                OPENWEATHER_URL,
                params={
                    "lat": settings.openweather_lat,
                    "lon": settings.openweather_lon,
                    "appid": settings.openweather_api_key,
                },
            )
            r.raise_for_status()
            payload = r.json()
            main = payload.get("weather", [{}])[0].get("main", "Clear")
            return CONDITION_MAP.get(main, "clear")
    except Exception as e:
        logger.warning("openweather fetch failed: %s", e)
        return None


async def _write_weather(condition: str) -> None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(AdminState).where(AdminState.id == 1))
        row = res.scalars().first()
        if row is None:
            row = AdminState(id=1, current_weather=condition, weather_source="openweather")
            session.add(row)
        else:
            row.current_weather = condition
            row.weather_source = "openweather"
        await session.commit()


async def weather_refresh_loop(stop_event: asyncio.Event) -> None:
    """Periodic loop that pulls OpenWeather and updates AdminState."""
    interval = max(60, settings.weather_refresh_minutes * 60)
    while not stop_event.is_set():
        cond = await fetch_openweather_condition()
        if cond is not None:
            try:
                await _write_weather(cond)
                logger.info("weather refreshed from OpenWeather: %s", cond)
            except Exception as e:
                logger.warning("failed to persist weather: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass  # normal tick
