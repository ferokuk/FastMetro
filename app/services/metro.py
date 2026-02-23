import heapq
import httpx
from typing import Dict, List, Tuple, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Station, Trip, EdgeType


async def fetch_metro_from_api() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.hh_metro_api_url)
        resp.raise_for_status()
        return resp.json()


STATION_FIXES: Dict[str, Dict[str, object]] = {
    "136.886": {"lng": 37.765556},                              # Чухлинка (МЦД-4)
    "135.875": {"lng": 38.2261},                                # Раменское (МЦД-3)
    "135.874": {"lng": 38.206667},                              # Фабричная (МЦД-3)
    "132.736": {"lat": 55.603056, "lng": 37.631944},            # Покровское (МЦД-2)
    "131.708": {"lat": 55.700833, "lng": 37.343611},            # Сколково (МЦД-1)
    "133.885": {"lat": 55.625350, "lng": 37.298306},            # Пыхтино (Солнц.)
    "132.731": {"lat": 55.685289, "lng": 37.733973},            # Люблино (МЦД-2)
    "1.681":   {"name": "Новомосковская"},                      # Новомосковская (Коммунарка) → Новомосковская
}


def _apply_station_fixes(stations: List[Station]) -> None:
    """Patch known incorrect coordinates / names from the HH API by station id."""
    for st in stations:
        fix = STATION_FIXES.get(st.id)
        if not fix:
            continue
        if "lat" in fix:
            st.lat = float(fix["lat"])
        if "lng" in fix:
            st.lng = float(fix["lng"])
        if "name" in fix:
            st.name = str(fix["name"])


# -------------------- Дополнительные станции (нет в HH API) --------------------
#
# Словарь станций, которые нужно добавить в БД вручную (МЦД, МЦК и т.д.).
# Поля: id (уникальный), name, line_id, line_name, line_color, lat, lng, order.

STATIONS_ADD: List[Dict[str, object]] = [
    {
        "id": "D2.Pechatniki",
        "name": "Печатники",
        "line_id": "D2",
        "line_name": "МЦД-2",
        "line_color": "#E74280",
        "lat": 55.68,
        "lng": 37.728338,
        "order": 0,
    },
]


def _apply_stations_add(stations: List[Station], station_by_id: Dict[str, Station]) -> None:
    """Добавить в списки станции из STATIONS_ADD."""
    for row in STATIONS_ADD:
        sid = str(row["id"])
        if sid in station_by_id:
            continue
        st = Station(
            id=sid,
            name=str(row["name"]),
            lat=float(row["lat"]),
            lng=float(row["lng"]),
            line_id=str(row["line_id"]),
            line_name=str(row["line_name"]),
            line_color=str(row.get("line_color", "#888888")),
            order=int(row.get("order", 0)),
        )
        stations.append(st)
        station_by_id[st.id] = st


# -------------------- Manual edge patches (ID-based) --------------------
#
# Все патчи используют конкретные station_id из HH API.
# Формат: (from_id, to_id, edge_type). Все рёбра двунаправленные.

EDGE_REMOVE: List[Tuple[str, str, EdgeType]] = [
    # Солнцевская линия: убираем ошибочные перегоны из API
    ("133.885", "133.468", EdgeType.same_line),   # Пыхтино — Деловой центр (Солнц.)
    ("133.470", "133.885", EdgeType.same_line),   # Парк Победы (Солнц.) — Пыхтино
    ("133.918", "133.613", EdgeType.same_line),   # Аэропорт Внуково — Рассказовка

    # Сколково — Мещерская (ложный transfer из API)
    ("131.708", "136.904", EdgeType.transfer),    # Сколково (МЦД-1) — Мещерская (МЦД-4)

    # Подольск — Марьина Роща (ложный same_line МЦД-2)
    ("132.743", "132.917", EdgeType.same_line),   # Подольск — Марьина Роща (МЦД-2)

    # Люблино — Текстильщики (МЦД-2, перегон через Печатники)
    ("132.731", "132.730", EdgeType.same_line),   # Люблино (МЦД-2) — Текстильщики (МЦД-2)

    # Новопеределкино — Переделкино: убираем автоматический перегон МЦД-4
    ("136.906", "136.907", EdgeType.same_line),   # Новопеределкино (МЦД-4) — Переделкино (МЦД-4)
    ("133.612", "136.907", EdgeType.same_line),   # Новопеределкино (Солнц.) — Переделкино (МЦД-4)
    ("133.613", "133.611", EdgeType.same_line),   # Рассказовка — Боровское шоссе
    ("133.613", "133.610", EdgeType.same_line),   # Рассказовка — Солнцево
    ("133.612", "133.610", EdgeType.same_line),   # Новопеределкино (Солнц.) — Солнцево

    # Люблино: убираем связь между ЛД и МЦД-2
    ("10.75", "132.731", EdgeType.same_line),     # Люблино (ЛД) — Люблино (МЦД-2)
    ("10.75", "132.731", EdgeType.transfer),      # Люблино (ЛД) — Люблино (МЦД-2)

    # Каховская: убираем ошибочные перегоны старой серой линии
    ("11.44", "9.156", EdgeType.same_line),       # Каховская (Каховск.) — Чертановская
    ("11.44", "9.43", EdgeType.same_line),        # Каховская (Каховск.) — Севастопольская
    ("97.818", "9.156", EdgeType.same_line),      # Каховская (БКЛ) — Чертановская
    ("97.818", "9.43", EdgeType.same_line),       # Каховская (БКЛ) — Севастопольская
]

EDGE_ADD: List[Tuple[str, str, EdgeType]] = [
    # --- Специальные перегоны Солнцевской линии ---
    ("133.918", "133.885", EdgeType.same_line),   # Аэропорт Внуково — Пыхтино
    ("133.885", "133.613", EdgeType.same_line),   # Пыхтино — Рассказовка
    ("133.470", "133.468", EdgeType.same_line),   # Парк Победы (Солнц.) — Деловой центр (Солнц.)

    # Жёлтая линия: Рассказовка → Новопеределкино (жёлт.) → Боровское шоссе
    ("133.613", "133.612", EdgeType.same_line),   # Рассказовка — Новопеределкино (Солнц.)
    ("133.612", "133.611", EdgeType.same_line),   # Новопеределкино (Солнц.) — Боровское шоссе

    # МЦД-4: Солнечная → Переделкино, Солнечная → Новопеределкино (зелёная)
    ("136.905", "136.907", EdgeType.same_line),   # Солнечная (МЦД-4) — Переделкино (МЦД-4)
    ("136.905", "136.906", EdgeType.same_line),   # Солнечная (МЦД-4) — Новопеределкино (МЦД-4)

    # Пересадка Солнечная (МЦД-4) <-> Солнечная... нет такой станции метро.
    # Если в API появится — добавим. Пока skip.

    # --- Центральное кольцо пересадок ---
    ("1.98", "2.99", EdgeType.transfer),          # Охотный ряд — Театральная
    ("2.99", "3.100", EdgeType.transfer),         # Театральная — Площадь Революции

    ("1.4", "3.5", EdgeType.transfer),            # Библиотека им.Ленина — Арбатская (АП)
    ("1.4", "4.6", EdgeType.transfer),            # Библиотека им.Ленина — Александровский сад
    ("1.4", "9.7", EdgeType.transfer),            # Библиотека им.Ленина — Боровицкая
    ("3.5", "4.6", EdgeType.transfer),            # Арбатская (АП) — Александровский сад
    ("3.5", "9.7", EdgeType.transfer),            # Арбатская (АП) — Боровицкая

    ("2.122", "7.124", EdgeType.transfer),        # Тверская — Пушкинская
    ("2.122", "9.123", EdgeType.transfer),        # Тверская — Чеховская
    ("7.124", "9.123", EdgeType.transfer),        # Пушкинская — Чеховская

    ("1.66", "7.67", EdgeType.transfer),          # Лубянка — Кузнецкий мост

    ("6.50", "7.51", EdgeType.transfer),          # Китай-город (КР) — Китай-город (ТКП)

    ("6.144", "1.143", EdgeType.transfer),        # Тургеневская — Чистые пруды
    ("6.144", "10.175", EdgeType.transfer),       # Тургеневская — Сретенский бульвар
    ("1.143", "10.175", EdgeType.transfer),       # Чистые пруды — Сретенский бульвар

    ("8.91", "6.90", EdgeType.transfer),          # Третьяковская (Калин.) — Третьяковская (КР)
    ("8.91", "2.89", EdgeType.transfer),          # Третьяковская (Калин.) — Новокузнецкая
    ("6.90", "2.89", EdgeType.transfer),          # Третьяковская (КР) — Новокузнецкая

    ("8.78", "7.77", EdgeType.transfer),          # Марксистская — Таганская (ТКП)
    ("5.76", "7.77", EdgeType.transfer),          # Таганская (Кольц.) — Таганская (ТКП)
    ("8.78", "5.76", EdgeType.transfer),          # Марксистская — Таганская (Кольц.)

    ("3.70", "5.71", EdgeType.transfer),          # Курская (АП) — Курская (Кольц.)
    ("3.70", "10.72", EdgeType.transfer),         # Курская (АП) — Чкаловская
    ("5.71", "10.72", EdgeType.transfer),         # Курская (Кольц.) — Чкаловская

    ("1.54", "5.55", EdgeType.transfer),          # Комсомольская (Сок.) — Комсомольская (Кольц.)
    ("6.120", "5.119", EdgeType.transfer),        # Проспект Мира (КР) — Проспект Мира (Кольц.)

    ("5.82", "9.83", EdgeType.transfer),          # Новослободская — Менделеевская
    ("2.19", "5.20", EdgeType.transfer),          # Белорусская (Замоскв.) — Белорусская (Кольц.)

    ("3.47", "4.48", EdgeType.transfer),          # Киевская (АП) — Киевская (Филёвская)
    ("3.47", "5.49", EdgeType.transfer),          # Киевская (АП) — Киевская (Кольц.)
    ("4.48", "5.49", EdgeType.transfer),          # Киевская (Филёвская) — Киевская (Кольц.)

    ("1.103", "5.104", EdgeType.transfer),        # Парк культуры (Сок.) — Парк культуры (Кольц.)
    ("6.94", "5.93", EdgeType.transfer),          # Октябрьская (КР) — Октябрьская (Кольц.)

    ("5.36", "9.37", EdgeType.transfer),          # Добрынинская — Серпуховская
    ("2.101", "5.102", EdgeType.transfer),        # Павелецкая (Замоскв.) — Павелецкая (Кольц.)

    ("5.58", "7.16", EdgeType.transfer),          # Краснопресненская — Баррикадная
    ("9.154", "10.177", EdgeType.transfer),       # Цветной бульвар — Трубная

    # --- Пересадки с БКЛ ---
    ("97.812", "133.607", EdgeType.same_line),    # Аминьевская (БКЛ) — Мичуринский проспект (Солнц.)
    ("9.128", "97.685", EdgeType.transfer),       # Савёловская (СТ) — Савёловская (БКЛ)
    ("10.185", "97.821", EdgeType.transfer),      # Марьина Роща (ЛД) — Марьина Роща (БКЛ)
    ("6.126", "97.822", EdgeType.transfer),       # Рижская (КР) — Рижская (БКЛ)
    ("1.134", "97.823", EdgeType.transfer),       # Сокольники (Сок.) — Сокольники (БКЛ)
    ("3.161", "97.803", EdgeType.transfer),       # Электрозаводская (АП) — Электрозаводская (БКЛ)
    ("8.1", "97.826", EdgeType.transfer),         # Авиамоторная (Калин.) — Авиамоторная (БКЛ)
    ("95.526", "97.827", EdgeType.transfer),      # Нижегородская (МЦК) — Нижегородская (БКЛ)
    ("98.765", "97.827", EdgeType.transfer),      # Нижегородская (Некр.) — Нижегородская (БКЛ)
    ("7.139", "97.828", EdgeType.transfer),       # Текстильщики (ТКП) — Текстильщики (БКЛ)
    ("10.109", "97.829", EdgeType.transfer),      # Печатники (ЛД) — Печатники (БКЛ)
    ("2.45", "97.832", EdgeType.transfer),        # Каширская (Замоскв.) — Каширская (БКЛ)
    ("11.46", "97.832", EdgeType.transfer),       # Каширская (Каховск.) — Каширская (БКЛ)
    ("97.818", "9.43", EdgeType.transfer),        # Каховская (БКЛ) — Севастопольская
    ("97.816", "6.41", EdgeType.transfer),        # Воронцовская (БКЛ) — Калужская
    ("97.815", "137.921", EdgeType.transfer),     # Новаторская (БКЛ) — Новаторская (Троицк.)
    ("1.118", "97.814", EdgeType.transfer),       # Проспект Вернадского (Сок.) — Проспект Вернадского (БКЛ)
    ("133.607", "97.813", EdgeType.transfer),     # Мичуринский проспект (Солнц.) — Мичуринский проспект (БКЛ)
    ("3.69", "97.810", EdgeType.transfer),        # Кунцевская (АП) — Кунцевская (БКЛ)
    ("4.471", "97.810", EdgeType.transfer),       # Кунцевская (Филёвская) — Кунцевская (БКЛ)
    ("97.601", "7.114", EdgeType.transfer),       # Хорошевская (БКЛ) — Полежаевская
    ("97.601", "95.539", EdgeType.transfer),      # Хорошевская (БКЛ) — Хорошево (МЦК)
    ("97.601", "97.806", EdgeType.same_line),     # Хорошевская (БКЛ) — Народное Ополчение (БКЛ)
    ("97.599", "2.34", EdgeType.transfer),        # Петровский парк (БКЛ) — Динамо

    # --- Радиальные / МЦК пересадки ---
    ("9.108", "10.548", EdgeType.transfer),       # Петровско-Разумовская (СТ) — (ЛД)
    ("2.57", "10.186", EdgeType.transfer),        # Красногвардейская — Зябликово
    ("7.62", "10.63", EdgeType.transfer),         # Пролетарская — Крестьянская застава
    ("8.112", "10.113", EdgeType.transfer),       # Площадь Ильича — Римская
    ("3.173", "133.470", EdgeType.transfer),      # Парк Победы (АП) — Парк Победы (Солнц.)
    ("3.69", "4.471", EdgeType.transfer),         # Кунцевская (АП) — Кунцевская (Филёвская)
    ("133.468", "4.172", EdgeType.transfer),      # Деловой центр (Солнц.) — Деловой центр (Выставочная)
    ("95.537", "133.468", EdgeType.transfer),     # Деловой центр (МЦК) — Деловой центр (Солнц.)
    ("95.537", "4.172", EdgeType.transfer),       # Деловой центр (МЦК) — Деловой центр (Выставочная)
    ("9.170", "12.171", EdgeType.transfer),       # Бульвар Дмитрия Донского — Улица Старокачаловская
    ("6.23", "12.467", EdgeType.transfer),        # Новоясеневская — Битцевский Парк
    ("7.464", "98.675", EdgeType.transfer),       # Лермонтовский проспект — Косино (Некр.)
    ("95.531", "137.964", EdgeType.transfer),     # ЗИЛ (МЦК) — ЗИЛ (Троицк.)
    ("95.533", "137.963", EdgeType.transfer),     # Крымская (МЦК) — Крымская (Троицк.)

    # --- Основные пересадки на МЦК ---
    ("6.74", "95.534", EdgeType.transfer),        # Ленинский проспект — Площадь Гагарина (МЦК)
    ("2.30", "95.543", EdgeType.transfer),        # Войковская — Балтийская (МЦК)
    ("6.24", "95.517", EdgeType.transfer),        # Ботанический сад (КР) — Ботанический сад (МЦК)
    ("9.28", "95.516", EdgeType.transfer),        # Владыкино (СТ) — Владыкино (МЦК)
    ("1.155", "95.521", EdgeType.transfer),       # Черкизовская — Локомотив (МЦК)
    ("1.148", "95.520", EdgeType.transfer),       # Бульвар Рокоссовского (Сок.) — (МЦК)
    ("8.158", "95.524", EdgeType.transfer),       # Шоссе Энтузиастов (Калин.) — (МЦК)
    ("10.39", "95.529", EdgeType.transfer),       # Дубровка (ЛД) — Дубровка (МЦК)
    ("2.2", "95.530", EdgeType.transfer),         # Автозаводская (Замоскв.) — Автозаводская (МЦК)
    ("1.135", "95.535", EdgeType.transfer),       # Спортивная — Лужники (МЦК)
    ("9.85", "95.532", EdgeType.transfer),        # Нагатинская — Верхние Котлы (МЦК)
    ("4.73", "95.536", EdgeType.transfer),        # Кутузовская (Филёвская) — Кутузовская (МЦК)
    ("95.538", "97.602", EdgeType.transfer),      # Шелепиха (МЦК) — Шелепиха (БКЛ)
    ("95.541", "7.95", EdgeType.transfer),        # Панфиловская (МЦК) — Октябрьское поле
    ("3.105", "95.522", EdgeType.transfer),       # Партизанская — Измайлово (МЦК)
    ("95.540", "7.95", EdgeType.transfer),        # Зорге (МЦК) — Октябрьское поле

    # --- МЦД-1 (Белорусско-Савёловский) ---
    ("131.801", "3.176", EdgeType.transfer),      # Славянский бульвар (МЦД-1) — (АП)
    ("131.703", "4.151", EdgeType.transfer),      # Фили (МЦД-1) — Фили (Филёвская)
    ("131.702", "4.172", EdgeType.transfer),      # Тестовская (МЦД-1) — Деловой центр (Выставочная) [≈Международная]
    ("131.702", "133.468", EdgeType.transfer),    # Тестовская (МЦД-1) — Деловой центр (Солнц.)
    ("131.701", "7.18", EdgeType.transfer),       # Беговая (МЦД-1) — Беговая (ТКП)
    ("131.698", "9.141", EdgeType.transfer),      # Тимирязевская (МЦД-1) — (СТ)
    ("131.697", "10.596", EdgeType.transfer),     # Окружная (МЦД-1) — Окружная (ЛД)
    ("131.697", "95.515", EdgeType.transfer),     # Окружная (МЦД-1) — Окружная (МЦК)
    ("131.694", "10.834", EdgeType.transfer),     # Лианозово (МЦД-1) — Лианозово (ЛД)
    ("131.700", "2.19", EdgeType.transfer),       # Белорусская (МЦД-1) — Белорусская (Замоскв.)
    ("131.700", "5.20", EdgeType.transfer),       # Белорусская (МЦД-1) — Белорусская (Кольц.)
    ("131.699", "9.128", EdgeType.transfer),      # Савёловская (МЦД-1) — Савёловская (СТ)
    ("131.699", "97.685", EdgeType.transfer),     # Савёловская (МЦД-1) — Савёловская (БКЛ)
    ("131.704", "3.69", EdgeType.transfer),       # Кунцевская (МЦД-1) — Кунцевская (АП)
    ("131.704", "4.471", EdgeType.transfer),      # Кунцевская (МЦД-1) — Кунцевская (Филёвская)
    ("131.704", "97.810", EdgeType.transfer),     # Кунцевская (МЦД-1) — Кунцевская (БКЛ)

    # --- МЦД-2 (Курско-Рижский) ---
    ("132.717", "3.182", EdgeType.transfer),      # Волоколамская (МЦД-2) — (АП)
    ("132.718", "7.145", EdgeType.transfer),      # Тушинская (МЦД-2) — (ТКП)
    ("132.720", "2.30", EdgeType.transfer),       # Стрешнево (МЦД-2) — Войковская
    ("132.720", "95.542", EdgeType.transfer),     # Стрешнево (МЦД-2) — Стрешнево (МЦК)
    ("132.723", "9.35", EdgeType.transfer),       # Дмитровская (МЦД-2) — (СТ)
    ("132.725", "1.54", EdgeType.transfer),       # Площадь трёх вокзалов (МЦД-2) — Комсомольская (Сок.)
    ("132.725", "5.55", EdgeType.transfer),       # Площадь трёх вокзалов (МЦД-2) — Комсомольская (Кольц.)
    ("132.726", "3.70", EdgeType.transfer),       # Курская (МЦД-2) — Курская (АП)
    ("132.726", "5.71", EdgeType.transfer),       # Курская (МЦД-2) — Курская (Кольц.)
    ("132.726", "10.72", EdgeType.transfer),      # Курская (МЦД-2) — Чкаловская
    ("132.727", "10.113", EdgeType.transfer),     # Москва Товарная (МЦД-2) — Римская
    ("132.727", "8.112", EdgeType.transfer),      # Москва Товарная (МЦД-2) — Площадь Ильича
    ("132.735", "2.153", EdgeType.transfer),      # Царицыно (МЦД-2) — Царицыно (Замоскв.)
    ("132.724", "6.126", EdgeType.transfer),      # Рижская (МЦД-2) — Рижская (КР)
    ("132.724", "97.822", EdgeType.transfer),     # Рижская (МЦД-2) — Рижская (БКЛ)
    ("132.917", "10.185", EdgeType.transfer),     # Марьина Роща (МЦД-2) — Марьина Роща (ЛД)
    ("132.917", "97.821", EdgeType.transfer),     # Марьина Роща (МЦД-2) — Марьина Роща (БКЛ)

    # Перегоны МЦД-2 через Печатники
    ("132.731", "D2.Pechatniki", EdgeType.same_line),  # Люблино (МЦД-2) — Печатники (МЦД-2)
    ("D2.Pechatniki", "132.730", EdgeType.same_line),  # Печатники (МЦД-2) — Текстильщики (МЦД-2)

    # --- МЦД-3 (Ленинградско-Казанский) ---
    ("135.845", "2.558", EdgeType.transfer),      # Ховрино (МЦД-3) — Ховрино (Замоскв.)
    ("135.848", "95.545", EdgeType.transfer),     # Лихоборы (МЦД-3) — Лихоборы (МЦК)
    ("135.850", "10.546", EdgeType.transfer),     # Останкино (МЦД-3) — Бутырская (ЛД)
    ("135.852", "1.134", EdgeType.transfer),      # Митьково (МЦД-3) — Сокольники (Сок.)
    ("135.852", "97.823", EdgeType.transfer),     # Митьково (МЦД-3) — Сокольники (БКЛ)
    ("135.853", "3.161", EdgeType.transfer),      # Электрозаводская (МЦД-3) — (АП)
    ("135.853", "97.803", EdgeType.transfer),     # Электрозаводская (МЦД-3) — (БКЛ)
    ("135.855", "8.1", EdgeType.transfer),        # Авиамоторная (МЦД-3) — (Калин.)
    ("135.855", "97.826", EdgeType.transfer),     # Авиамоторная (МЦД-3) — (БКЛ)
    ("135.856", "95.525", EdgeType.transfer),     # Андроновка (МЦД-3) — Андроновка (МЦК)
    ("135.859", "7.127", EdgeType.transfer),      # Вешняки (МЦД-3) — Рязанский проспект
    ("135.860", "7.33", EdgeType.transfer),       # Выхино (МЦД-3) — Выхино (ТКП)
    ("135.861", "98.675", EdgeType.transfer),     # Косино (МЦД-3) — Косино (Некр.)
    ("135.849", "9.108", EdgeType.transfer),      # Петровско-Разумовская (МЦД-3) — (СТ)
    ("135.849", "10.548", EdgeType.transfer),     # Петровско-Разумовская (МЦД-3) — (ЛД)
    ("135.851", "6.126", EdgeType.transfer),      # Рижская (МЦД-3) — Рижская (КР)
    ("135.851", "97.822", EdgeType.transfer),     # Рижская (МЦД-3) — Рижская (БКЛ)

    # --- МЦД-4 (Калужско-Нижегородский) ---
    ("136.902", "97.812", EdgeType.transfer),     # Аминьевская (МЦД-4) — Аминьевская (БКЛ)
    ("136.900", "133.555", EdgeType.transfer),    # Минская (МЦД-4) — Минская (Солнц.)
    ("136.899", "3.173", EdgeType.transfer),      # Поклонная (МЦД-4) — Парк Победы (АП)
    ("136.899", "133.470", EdgeType.transfer),    # Поклонная (МЦД-4) — Парк Победы (Солнц.)
    ("136.888", "8.112", EdgeType.transfer),      # Серп и Молот (МЦД-4) — Площадь Ильича
    ("136.888", "10.113", EdgeType.transfer),     # Серп и Молот (МЦД-4) — Римская
    ("136.886", "135.857", EdgeType.transfer),    # Чухлинка (МЦД-4) — Перово (МЦД-3)
    ("136.883", "8.88", EdgeType.transfer),       # Новогиреево (МЦД-4) — Новогиреево (Калин.)
    ("136.882", "8.189", EdgeType.transfer),      # Реутов (МЦД-4) — Новокосино (Калин.)
    ("136.887", "97.827", EdgeType.transfer),     # Нижегородская (МЦД-4) — Нижегородская (БКЛ)
    ("136.887", "98.765", EdgeType.transfer),     # Нижегородская (МЦД-4) — Нижегородская (Некр.)
    ("136.887", "95.526", EdgeType.transfer),     # Нижегородская (МЦД-4) — Нижегородская (МЦК)
    ("136.889", "3.70", EdgeType.transfer),       # Курская (МЦД-4) — Курская (АП)
    ("136.889", "5.71", EdgeType.transfer),       # Курская (МЦД-4) — Курская (Кольц.)
    ("136.889", "10.72", EdgeType.transfer),      # Курская (МЦД-4) — Чкаловская
    ("136.890", "1.54", EdgeType.transfer),       # Площадь трёх вокзалов (МЦД-4) — Комсомольская (Сок.)
    ("136.890", "5.55", EdgeType.transfer),       # Площадь трёх вокзалов (МЦД-4) — Комсомольская (Кольц.)
    ("136.891", "6.126", EdgeType.transfer),      # Рижская (МЦД-4) — Рижская (КР)
    ("136.891", "97.822", EdgeType.transfer),     # Рижская (МЦД-4) — Рижская (БКЛ)
    ("136.892", "10.185", EdgeType.transfer),     # Марьина Роща (МЦД-4) — Марьина Роща (ЛД)
    ("136.892", "97.821", EdgeType.transfer),     # Марьина Роща (МЦД-4) — Марьина Роща (БКЛ)
    ("136.893", "9.128", EdgeType.transfer),      # Савёловская (МЦД-4) — Савёловская (СТ)
    ("136.893", "97.685", EdgeType.transfer),     # Савёловская (МЦД-4) — Савёловская (БКЛ)
    ("136.894", "2.19", EdgeType.transfer),       # Белорусская (МЦД-4) — Белорусская (Замоскв.)
    ("136.894", "5.20", EdgeType.transfer),       # Белорусская (МЦД-4) — Белорусская (Кольц.)
    ("136.897", "4.172", EdgeType.transfer),      # Тестовская (МЦД-4) — Деловой центр (Выставочная)
    ("136.897", "133.468", EdgeType.transfer),    # Тестовская (МЦД-4) — Деловой центр (Солнц.)
    ("136.898", "4.73", EdgeType.transfer),       # Кутузовская (МЦД-4) — Кутузовская (Филёвская)
    ("136.898", "95.536", EdgeType.transfer),     # Кутузовская (МЦД-4) — Кутузовская (МЦК)
    ("D2.Pechatniki", "10.109", EdgeType.transfer),  # Печатники (МЦД-2) — Печатники (ЛД)
    ("D2.Pechatniki", "97.829", EdgeType.transfer),  # Печатники (МЦД-2) — Печатники (БКЛ)
]


def _apply_edge_patches(stations: List[Station], trips: List[Trip]) -> List[Trip]:
    """Apply manual add/remove patches by station ID."""
    if not EDGE_REMOVE and not EDGE_ADD:
        return trips

    remove_set: set[Tuple[str, str, EdgeType]] = set()
    for a, b, et in EDGE_REMOVE:
        remove_set.add((a, b, et))
        remove_set.add((b, a, et))

    filtered: List[Trip] = [
        t for t in trips
        if (t.from_station_id, t.to_station_id, t.edge_type) not in remove_set
    ]

    for a, b, et in EDGE_ADD:
        filtered.append(Trip(from_station_id=a, to_station_id=b, edge_type=et))
        filtered.append(Trip(from_station_id=b, to_station_id=a, edge_type=et))

    return filtered


async def enrich_database(session: AsyncSession) -> Tuple[int, int]:
    """Fetch metro from HH API, fill stations and trips. Returns (stations_count, trips_count)."""
    data = await fetch_metro_from_api()

    # Clear existing
    await session.execute(delete(Trip))
    await session.execute(delete(Station))
    await session.commit()

    stations: List[Station] = []
    station_by_id: Dict[str, Station] = {}

    for line in data.get("lines", []):
        line_id = str(line["id"])
        line_name = line["name"]
        hex_color = line.get("hex_color", "888888")
        line_color = f"#{hex_color}" if not hex_color.startswith("#") else hex_color
        for s in line.get("stations", []):
            st = Station(
                id=str(s["id"]),
                name=s["name"],
                lat=float(s["lat"]),
                lng=float(s["lng"]),
                line_id=line_id,
                line_name=line_name,
                line_color=line_color,
                order=int(s["order"]),
            )
            stations.append(st)
            station_by_id[st.id] = st

    _apply_station_fixes(stations)
    _apply_stations_add(stations, station_by_id)
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

    # Применяем id-based патчи (EDGE_ADD / EDGE_REMOVE)
    trips = _apply_edge_patches(stations, trips)
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
