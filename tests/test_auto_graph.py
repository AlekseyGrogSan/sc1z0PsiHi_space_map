import pytest
from httpx import AsyncClient

from app.services.auto_graph import generate_auto_graph, is_segment_clear


def test_is_segment_clear_obstacle_detection():
    # Стена от (100, 0) до (100, 200)
    walls = [{"x1": 100.0, "y1": 0.0, "x2": 100.0, "y2": 200.0}]
    # Отрезок, пересекающий стену
    assert not is_segment_clear((50.0, 100.0), (150.0, 100.0), walls, [], [])
    # Отрезок, не пересекающий стену
    assert is_segment_clear((50.0, 50.0), (50.0, 150.0), walls, [], [])

    # Круглое препятствие в (100, 100) радиусом 30
    circles = [{"x": 100.0, "y": 100.0, "radius": 30.0}]
    # Отрезок, проходящий через центр круга
    assert not is_segment_clear((50.0, 100.0), (150.0, 100.0), [], circles, [])
    # Отрезок, проходящий мимо круга на безопасном расстоянии
    assert is_segment_clear((50.0, 200.0), (150.0, 200.0), [], circles, [])


def test_generate_auto_graph_bypasses_circular_obstacle():
    layout = {
        "obstacles": [
            {"id": "col-1", "type": "circle", "x": 500, "y": 500, "radius": 40}
        ],
        "walls": [
            {"x1": 300, "y1": 200, "x2": 700, "y2": 200}
        ],
        "corridors": [
            {"x1": 100, "y1": 500, "x2": 900, "y2": 500}
        ],
    }
    mock_pois = [
        {"x": 100, "y": 500, "category": "entrance", "title": "Вход"},
        {"x": 900, "y": 500, "category": "bench", "title": "Лавочка"},
    ]

    nodes, edges = generate_auto_graph(1000, 1000, layout, mock_pois)

    assert len(nodes) > 10
    # Проверяем, что созданы узлы обхода вокруг колонны
    circle_nodes = [n for n in nodes if math_dist(n["x"], n["y"], 500, 500) < 100]
    assert len(circle_nodes) >= 8

    # Проверяем, что ни одно ребро не прорезает круглую колонну радиусом 40
    for i1, i2 in edges:
        p1 = (nodes[i1]["x"], nodes[i1]["y"])
        p2 = (nodes[i2]["x"], nodes[i2]["y"])
        assert is_segment_clear(p1, p2, [], [{"x": 500, "y": 500, "radius": 39}], [])


def math_dist(x1, y1, x2, y2):
    import math
    return math.hypot(x2 - x1, y2 - y1)


@pytest.mark.asyncio
async def test_auto_graph_api_and_route_around_corner(client: AsyncClient, auth_headers: dict):
    # 1. Создаем пространство
    space_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Торговый центр 2D", "slug": "tc-2d"},
    )
    space_id = space_resp.json()["id"]

    # 2. Создаем этаж с 2D-планировкой (стена-препятствие и поворот)
    layout = {
        "walls": [
            {"x1": 400, "y1": 0, "x2": 400, "y2": 600}
        ],
        "obstacles": [
            {"type": "circle", "x": 600, "y": 600, "radius": 35}
        ]
    }
    floor_resp = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={
            "floor_number": 1,
            "title": "1 этаж",
            "ppm": 20.0,
            "layout_data": layout,
        },
    )
    floor_id = floor_resp.json()["id"]

    # 3. Добавляем вход и лавочку по разные стороны стены
    entrance_resp = await client.post(
        f"/api/v1/floors/{floor_id}/pois",
        headers=auth_headers,
        json={"title": "Главный вход", "category": "entrance", "x_coord": 200.0, "y_coord": 300.0},
    )
    bench_resp = await client.post(
        f"/api/v1/floors/{floor_id}/pois",
        headers=auth_headers,
        json={"title": "Лавочка отдыха", "category": "bench", "x_coord": 600.0, "y_coord": 300.0},
    )
    bench_id = bench_resp.json()["id"]

    # 4. Вызываем автогенерацию графа
    auto_resp = await client.post(
        f"/api/v1/floors/{floor_id}/navigation/auto-graph",
        headers=auth_headers,
    )
    assert auto_resp.status_code == 200
    graph = auto_resp.json()["graph"]
    assert len(graph["nodes"]) > 0
    assert len(graph["edges"]) > 0

    # 5. Строим маршрут от входа до лавочки (должен огибать стену снизу)
    route_resp = await client.post(
        f"/api/v1/spaces/{space_id}/navigation/route",
        json={
            "floor_id": floor_id,
            "x": 200.0,
            "y": 300.0,
            "to_poi_id": bench_id,
        },
    )
    assert route_resp.status_code == 200
    route = route_resp.json()
    assert "points" in route
    assert len(route["points"]) >= 2
    assert route["total_distance_meters"] > 0


@pytest.mark.asyncio
async def test_route_from_room_to_room_arbitrary_start_avoids_walls(
    client: AsyncClient, auth_headers: dict
):
    """
    Проверяет сценарий из баг-репорта (Лёша/Вадим):
    Маршрут из произвольной точки Комнаты 2 в Комнату 1 должен
    проходить через дверной проём и огибать стены, а не резать стены напрямую.
    """
    # 1. Создаем пространство
    space_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Офис двух зон", "slug": "office-2rooms"},
    )
    space_id = space_resp.json()["id"]

    # 2. Планировка двух комнат (Зона 2 сверху-слева, Зона 1 снизу-справа с проходом)
    layout = {
        "rooms": [
            {"id": "r1", "title": "ЗОНА 2", "x": 350, "y": 380, "width": 270, "height": 130},
            {"id": "r2", "title": "ЗОНА 1", "x": 570, "y": 500, "width": 220, "height": 270},
        ],
        "walls": [
            # Зона 2: стены с дверным проходом справа (y: 440..510)
            {"x1": 350, "y1": 380, "x2": 620, "y2": 380},
            {"x1": 350, "y1": 380, "x2": 350, "y2": 510},
            {"x1": 350, "y1": 510, "x2": 620, "y2": 510},  # глухая разделяющая стена между Зоной 2 и коридором
            {"x1": 620, "y1": 380, "x2": 620, "y2": 440},  # проход 440..510
            # Зона 1: стены со входом сверху (x: 570..640) и входом снизу
            {"x1": 640, "y1": 500, "x2": 790, "y2": 500},
            {"x1": 790, "y1": 500, "x2": 790, "y2": 770},
            {"x1": 790, "y1": 770, "x2": 660, "y2": 770},
            {"x1": 570, "y1": 770, "x2": 600, "y2": 770},
            {"x1": 570, "y1": 500, "x2": 570, "y2": 770},
        ],
        "corridors": [],
        "obstacles": [],
    }

    floor_resp = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={
            "floor_number": 1,
            "title": "1 этаж",
            "ppm": 20.0,
            "layout_data": layout,
        },
    )
    floor_id = floor_resp.json()["id"]

    # 3. Добавляем POI: Стол в Зоне 2 и Вход в Зоне 1
    table_resp = await client.post(
        f"/api/v1/floors/{floor_id}/pois",
        headers=auth_headers,
        json={"title": "Стол", "category": "info", "x_coord": 550.0, "y_coord": 420.0},
    )
    entrance_resp = await client.post(
        f"/api/v1/floors/{floor_id}/pois",
        headers=auth_headers,
        json={"title": "Вход", "category": "entrance", "x_coord": 630.0, "y_coord": 770.0},
    )
    entrance_id = entrance_resp.json()["id"]

    # 4. Автогенерация графа
    auto_resp = await client.post(
        f"/api/v1/floors/{floor_id}/navigation/auto-graph",
        headers=auth_headers,
    )
    assert auto_resp.status_code == 200

    # 5. Проверяем построение маршрута из произвольной точки Зоны 2 (400, 450)
    route_resp = await client.post(
        f"/api/v1/spaces/{space_id}/navigation/route",
        json={
            "floor_id": floor_id,
            "x": 400.0,
            "y": 450.0,
            "to_poi_id": entrance_id,
        },
    )
    assert route_resp.status_code == 200
    route = route_resp.json()
    assert route["total_distance_meters"] > 0
    points = route["points"]
    assert len(points) >= 3  # Маршрут должен огибать стену через проём, а не быть прямой линией из 2 точек

    # Проверяем, что ни один отрезок маршрута не режет сплошную стену (350..620, y=510)
    dividing_wall = {"x1": 350.0, "y1": 510.0, "x2": 620.0, "y2": 510.0}
    for k in range(len(points) - 1):
        p1 = (points[k]["x"], points[k]["y"])
        p2 = (points[k + 1]["x"], points[k + 1]["y"])
        assert is_segment_clear(p1, p2, [dividing_wall], [], []), f"Отрезок {p1}->{p2} режет стену!"
