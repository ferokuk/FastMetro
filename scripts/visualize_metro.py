#!/usr/bin/env python3
"""
Визуализация графа метро Москвы: станции и связи (перегоны + переходы).
Позволяет увидеть упущенные связи и визуально оценить маршруты.

Использование:
  python scripts/visualize_metro.py                    # граф в metro_graph.html
  python scripts/visualize_metro.py -o my_graph.html   # свой файл
  python scripts/visualize_metro.py --from-id 1.148 --to-id 2.89  # с подсветкой пути
"""
import argparse
import math
import sys
from pathlib import Path

import httpx

# Корень проекта в path (для запуска из любой папки)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API_URL = "https://api.hh.ru/metro/1"
TRANSFER_THRESHOLD = 0.001
MINUTES_SEGMENT = 3.0
MINUTES_TRANSFER = 6.0


def distance_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2)


def fetch_metro() -> dict:
    resp = httpx.get(API_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_stations_and_edges(data: dict):
    """Станции: list of dict id, name, lat, lng, line_id, line_name, hex_color. Рёбра: (a_id, b_id, is_transfer)."""
    stations = []
    station_by_id = {}
    for line in data.get("lines", []):
        line_id = str(line["id"])
        line_name = line["name"]
        hex_color = line.get("hex_color", "888888")
        for s in line.get("stations", []):
            sid = str(s["id"])
            st = {
                "id": sid,
                "name": s["name"],
                "lat": float(s["lat"]),
                "lng": float(s["lng"]),
                "line_id": line_id,
                "line_name": line_name,
                "hex_color": hex_color,
            }
            stations.append(st)
            station_by_id[sid] = st

    edges = []
    # Перегоны по линиям
    for line in data.get("lines", []):
        line_stations = line.get("stations", [])
        for i in range(len(line_stations) - 1):
            a_id = str(line_stations[i]["id"])
            b_id = str(line_stations[i + 1]["id"])
            edges.append((a_id, b_id, False))
            edges.append((b_id, a_id, False))
    # Переходы: расстояние < порога
    for i, a in enumerate(stations):
        for b in stations[i + 1 :]:
            if a["line_id"] == b["line_id"]:
                continue
            if distance_deg(a["lat"], a["lng"], b["lat"], b["lng"]) < TRANSFER_THRESHOLD:
                edges.append((a["id"], b["id"], True))
                edges.append((b["id"], a["id"], True))

    return stations, edges, station_by_id


def shortest_path_by_time(station_by_id, edges_list, start_id: str, end_id: str):
    """Дейкстра: 3 мин перегон, 6 мин переход. Возвращает (path_node_ids, total_minutes) или None."""
    if start_id not in station_by_id or end_id not in station_by_id:
        return None
    if start_id == end_id:
        return ([start_id], 0.0)
    # Граф: node -> [(neighbor, minutes), ...]
    graph = {}
    for sid in station_by_id:
        graph[sid] = []
    for a, b, is_transfer in edges_list:
        w = MINUTES_TRANSFER if is_transfer else MINUTES_SEGMENT
        graph[a].append((b, w))
    import heapq
    best = {start_id: 0.0}
    heap = [(0.0, start_id, [start_id])]
    while heap:
        t, cur, path = heapq.heappop(heap)
        if cur == end_id:
            return (path, t)
        if t > best.get(cur, float("inf")):
            continue
        for neighbor, w in graph[cur]:
            tn = t + w
            if tn < best.get(neighbor, float("inf")):
                best[neighbor] = tn
                heapq.heappush(heap, (tn, neighbor, path + [neighbor]))
    return None


def latlng_to_xy(lat: float, lng: float, center_lat: float = 55.75, center_lng: float = 37.62, scale: float = 800):
    """Преобразование в экранные координаты для pyvis (север вверх)."""
    x = (lng - center_lng) * scale
    y = (center_lat - lat) * scale
    return x, y


def main():
    parser = argparse.ArgumentParser(description="Визуализация графа московского метро")
    parser.add_argument("-o", "--output", default="metro_graph.html", help="Файл HTML для вывода")
    parser.add_argument("--from-id", help="ID станции начала пути (подсветка маршрута)")
    parser.add_argument("--to-id", help="ID станции конца пути (подсветка маршрута)")
    args = parser.parse_args()

    print("Загрузка данных с API...")
    data = fetch_metro()
    stations, edges_list, station_by_id = build_stations_and_edges(data)
    print(f"Станций: {len(stations)}, рёбер: {len(edges_list)}")

    path_ids = None
    path_edges = set()
    if args.from_id and args.to_id:
        result = shortest_path_by_time(station_by_id, edges_list, args.from_id, args.to_id)
        if result:
            path_ids, total_min = result
            path_edges = set()
            for i in range(len(path_ids) - 1):
                path_edges.add((path_ids[i], path_ids[i + 1]))
                path_edges.add((path_ids[i + 1], path_ids[i]))
            print(f"Маршрут: {len(path_ids)} станций, время ~{total_min:.0f} мин")
        else:
            print("Маршрут не найден, строится только граф.")

    try:
        from pyvis.network import Network
    except ImportError:
        print("Установите зависимости: pip install pyvis networkx")
        sys.exit(1)

    net = Network(
        height="900px",
        width="100%",
        bgcolor="#1a1a1a",
        font_color="#eee",
        directed=False,
    )
    # Текст только в подсказке (title при наведении), граф можно двигать и зумить
    net.set_options("""
    var options = {
      "nodes": {
        "font": { "size": 0 },
        "borderWidth": 1,
        "shadow": false,
        "size": 4
      },
      "edges": {
        "width": 1,
        "smooth": { "type": "continuous" }
      },
      "physics": {
        "enabled": false
      },
      "interaction": {
        "hover": true,
        "hoverConnectedEdges": true,
        "tooltipDelay": 50,
        "dragNodes": true,
        "dragView": true,
        "zoomView": true,
        "navigationButtons": true,
        "keyboard": { "enabled": true }
      }
    }
    """)

    center_lat = 55.75
    center_lng = 37.62
    scale = 800

    for st in stations:
        x, y = latlng_to_xy(st["lat"], st["lng"], center_lat, center_lng, scale)
        # Название и линия только в подсказке при наведении (title)
        title = f"{st['name']}\n{st['line_name']}"
        color = f"#{st['hex_color']}" if st.get("hex_color") else "#888"
        net.add_node(
            st["id"],
            label=" ",  # без подписи — только точка; при наведении показывается title
            title=title,
            x=x,
            y=y,
            color=color,
            size=10 if path_ids and st["id"] in path_ids else 5,
        )

    edge_set = set()
    for a_id, b_id, is_transfer in edges_list:
        key = (min(a_id, b_id), max(a_id, b_id))
        if key in edge_set:
            continue
        edge_set.add(key)
        on_path = (a_id, b_id) in path_edges or (b_id, a_id) in path_edges
        if on_path:
            net.add_edge(a_id, b_id, color="#ffcc00", width=4, title="Маршрут")
        elif is_transfer:
            # Переходы: яркий цвет, пунктир, толще — хорошо видны на графе
            net.add_edge(a_id, b_id, color="#00bcd4", width=2.5, dashes=True, title="Переход")
        else:
            net.add_edge(a_id, b_id, color="#444", width=0.8, title="Перегон")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    net.save_graph(str(out_path))
    print(f"Граф сохранён: {out_path.absolute()}")
    print("В браузере: двигайте граф мышью, колёсико — zoom. Наведение на узел — подсказка с названием.")
    print("Линии: серые — перегоны, голубые пунктирные — переходы.")


if __name__ == "__main__":
    main()
