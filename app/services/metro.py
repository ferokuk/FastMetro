import heapq
import httpx
import math
from typing import Dict, List, Tuple, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Station, Trip, EdgeType


def distance_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Euclidean distance in degrees (for transfer threshold 0.001)."""
    return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2)


async def fetch_metro_from_api() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.hh_metro_api_url)
        resp.raise_for_status()
        return resp.json()


async def enrich_database(session: AsyncSession) -> Tuple[int, int]:
    """Fetch metro from HH API, fill stations and trips. Returns (stations_count, trips_count)."""
    data = await fetch_metro_from_api()
    threshold = settings.transfer_distance_threshold

    # Clear existing
    await session.execute(delete(Trip))
    await session.execute(delete(Station))
    await session.commit()

    stations: List[Station] = []
    station_by_id: Dict[str, Station] = {}

    for line in data.get("lines", []):
        line_id = str(line["id"])
        line_name = line["name"]
        for s in line.get("stations", []):
            st = Station(
                id=str(s["id"]),
                name=s["name"],
                lat=float(s["lat"]),
                lng=float(s["lng"]),
                line_id=line_id,
                line_name=line_name,
                order=int(s["order"]),
            )
            stations.append(st)
            station_by_id[st.id] = st

    session.add_all(stations)
    await session.flush()

    trips: List[Trip] = []

    # Same-line edges: consecutive stations
    for line in data.get("lines", []):
        line_stations = line.get("stations", [])
        for i in range(len(line_stations) - 1):
            a_id = str(line_stations[i]["id"])
            b_id = str(line_stations[i + 1]["id"])
            trips.append(
                Trip(from_station_id=a_id, to_station_id=b_id, edge_type=EdgeType.same_line)
            )
            trips.append(
                Trip(from_station_id=b_id, to_station_id=a_id, edge_type=EdgeType.same_line)
            )

    # Transfers: any two stations with distance < threshold
    for i, a in enumerate(stations):
        for b in stations[i + 1 :]:
            if a.line_id == b.line_id:
                continue
            if distance_deg(a.lat, a.lng, b.lat, b.lng) < threshold:
                trips.append(
                    Trip(
                        from_station_id=a.id,
                        to_station_id=b.id,
                        edge_type=EdgeType.transfer,
                    )
                )
                trips.append(
                    Trip(
                        from_station_id=b.id,
                        to_station_id=a.id,
                        edge_type=EdgeType.transfer,
                    )
                )

    session.add_all(trips)
    await session.commit()
    return len(stations), len(trips)


def build_graph(
    stations: List[Station], trips: List[Trip]
) -> Dict[str, List[Tuple[str, bool]]]:
    """Build adjacency list: station_id -> [(neighbor_id, is_transfer), ...]."""
    graph: Dict[str, List[Tuple[str, bool]]] = {s.id: [] for s in stations}
    for t in trips:
        is_transfer = t.edge_type == EdgeType.transfer
        graph[t.from_station_id].append((t.to_station_id, is_transfer))
    return graph


def _edge_minutes(is_transfer: bool) -> float:
    return settings.minutes_per_transfer if is_transfer else settings.minutes_per_segment


def shortest_path_by_time(
    graph: Dict[str, List[Tuple[str, bool]]],
    station_by_id: Dict[str, Station],
    start_id: str,
    end_id: str,
) -> Optional[Tuple[List[Tuple[str, bool]], float]]:
    """
    Кратчайший путь по времени в пути (Дейкстра).
    Мок: 3 мин — перегон, 6 мин — переход.
    Returns (path, total_minutes) or None. path = [(station_id, is_transfer_into_this_station), ...].
    """
    if start_id not in graph or end_id not in graph:
        return None
    if start_id == end_id:
        return ([(start_id, False)], 0.0)

    # (total_time, node_id, path)
    best: Dict[str, float] = {start_id: 0.0}
    heap: List[Tuple[float, str, List[Tuple[str, bool]]]] = [(0.0, start_id, [(start_id, False)])]
    while heap:
        time_cur, cur, path = heapq.heappop(heap)
        if cur == end_id:
            return (path, time_cur)
        if time_cur > best.get(cur, float("inf")):
            continue
        for neighbor, is_transfer in graph[cur]:
            w = _edge_minutes(is_transfer)
            time_next = time_cur + w
            if time_next < best.get(neighbor, float("inf")):
                best[neighbor] = time_next
                heapq.heappush(heap, (time_next, neighbor, path + [(neighbor, is_transfer)]))
    return None


async def get_shortest_path(
    session: AsyncSession, from_station_id: str, to_station_id: str
) -> Optional[dict]:
    """Load stations and trips, compute shortest path, return path info for response."""
    st_stations = await session.execute(select(Station))
    stations = list(st_stations.scalars().all())
    st_trips = await session.execute(select(Trip))
    trips = list(st_trips.scalars().all())

    station_by_id = {s.id: s for s in stations}
    graph = build_graph(stations, trips)
    result_path = shortest_path_by_time(
        graph, station_by_id, from_station_id, to_station_id
    )
    if not result_path:
        return None
    path, total_minutes = result_path
    return {
        "path": path,
        "total_minutes": total_minutes,
        "station_by_id": station_by_id,
        "from_station": station_by_id[from_station_id],
        "to_station": station_by_id[to_station_id],
    }
