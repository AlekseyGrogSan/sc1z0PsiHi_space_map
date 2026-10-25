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


@pytest.mark.asyncio
async def test_route_between_rooms_with_many_walls_and_partitions(
    client: AsyncClient, auth_headers: dict
):
    """
    Проверяет, что при сложной планировке с множеством внутренних стен и перегородок
    (комнаты разделены на боксы/кабинеты и соединены дверным проёмом)
    маршрут между комнатами успешно строится через дверные проёмы и огибает все перегородки.
    """
    # 1. Пространство и этаж
    space_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Бизнес-центр со множеством стен", "slug": "many-walls-bc"},
    )
    space_id = space_resp.json()["id"]

    layout = {
        "rooms": [
            {"id": "room_a", "title": "Офис А", "x": 100, "y": 100, "width": 300, "height": 400},
            {"id": "room_b", "title": "Офис Б", "x": 450, "y": 100, "width": 350, "height": 400},
        ],
        "walls": [
            # Внешние стены Офиса А
            {"x1": 100, "y1": 100, "x2": 400, "y2": 100},
            {"x1": 100, "y1": 100, "x2": 100, "y2": 500},
            {"x1": 100, "y1": 500, "x2": 400, "y2": 500},
            # Разделительная стена Офиса А с дверным проемом справа (y: 260..340)
            {"x1": 400, "y1": 100, "x2": 400, "y2": 260},
            {"x1": 400, "y1": 340, "x2": 400, "y2": 500},
            # Внутренние стены-перегородки Офиса А (кабинеты)
            {"x1": 100, "y1": 200, "x2": 280, "y2": 200},  # перегородка 1
            {"x1": 100, "y1": 350, "x2": 280, "y2": 350},  # перегородка 2
            {"x1": 280, "y1": 200, "x2": 280, "y2": 260},  # перегородка 3

            # Внешние стены Офиса Б со входом слева (x: 450, y: 260..340)
            {"x1": 450, "y1": 100, "x2": 800, "y2": 100},
            {"x1": 800, "y1": 100, "x2": 800, "y2": 500},
            {"x1": 450, "y1": 500, "x2": 800, "y2": 500},
            {"x1": 450, "y1": 100, "x2": 450, "y2": 260},
            {"x1": 450, "y1": 340, "x2": 450, "y2": 500},
            # Внутренние стены-перегородки Офиса Б (кабинеты)
            {"x1": 580, "y1": 100, "x2": 580, "y2": 300},  # перегородка 4
            {"x1": 580, "y1": 380, "x2": 580, "y2": 500},  # перегородка 5
            {"x1": 680, "y1": 200, "x2": 800, "y2": 200},  # перегородка 6
        ],
        "corridors": [
            # Коридорный проход между двумя офисами
            {"x1": 400, "y1": 300, "x2": 450, "y2": 300, "width": 60},
        ],
        "obstacles": [],
    }

    floor_resp = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={
            "floor_number": 1,
            "title": "1 этаж со стенами",
            "ppm": 20.0,
            "layout_data": layout,
        },
    )
    floor_id = floor_resp.json()["id"]

    # Точка в глубине кабинета Офиса Б
    poi_resp = await client.post(
        f"/api/v1/floors/{floor_id}/pois",
        headers=auth_headers,
        json={"title": "Кабинет Директора", "category": "stand", "x_coord": 750.0, "y_coord": 150.0},
    )
    poi_id = poi_resp.json()["id"]

    # Автогенерация графа
    auto_resp = await client.post(
        f"/api/v1/floors/{floor_id}/navigation/auto-graph",
        headers=auth_headers,
    )
    assert auto_resp.status_code == 200
    graph = auto_resp.json()["graph"]
    assert len(graph["nodes"]) > 10

    # Строим маршрут из дальнего угла Офиса А (150, 150) за перегородками до Директора (750, 150)
    route_resp = await client.post(
        f"/api/v1/spaces/{space_id}/navigation/route",
        json={
            "floor_id": floor_id,
            "x": 150.0,
            "y": 150.0,
            "to_poi_id": poi_id,
        },
    )
    assert route_resp.status_code == 200, f"Маршрут не построен: {route_resp.text}"
    route = route_resp.json()
    assert route["total_distance_meters"] > 0
    points = route["points"]
    assert len(points) >= 4  # Должен пройти несколько поворотов вокруг стен и проём

    # Проверяем, что ни одно ребро маршрута не пересекает ни одну стену
    for k in range(len(points) - 1):
        p1 = (points[k]["x"], points[k]["y"])
        p2 = (points[k + 1]["x"], points[k + 1]["y"])
        assert is_segment_clear(p1, p2, layout["walls"], [], []), f"Ребро {p1}->{p2} режет стену!"


def test_auto_graph_handles_negative_and_extended_coordinates():
    """
    Проверяет, что при отрицательных координатах (например, комната слева от 0)
    узлы не сжимаются в 10.0 и граф корректно строится в отрицательной области.
    """
    layout = {
        "rooms": [
            {"id": "r1", "title": "ЗОНА 1", "x": -400, "y": 100, "width": 300, "height": 300},
            {"id": "r2", "title": "ЗОНА 2", "x": 100, "y": 100, "width": 300, "height": 300},
        ],
        "walls": [
            {"x1": -400, "y1": 100, "x2": -100, "y2": 100},
            {"x1": -400, "y1": 400, "x2": -100, "y2": 400},
            {"x1": -400, "y1": 100, "x2": -400, "y2": 400},
            {"x1": -100, "y1": 100, "x2": -100, "y2": 220},  # дверной проём 220..280
            {"x1": -100, "y1": 280, "x2": -100, "y2": 400},
        ],
        "corridors": [
            {"x1": -100, "y1": 250, "x2": 100, "y2": 250},
        ],
        "obstacles": [
            {"type": "circle", "x": -250, "y": 250, "radius": 30},
        ],
    }
    mock_pois = [
        {"x": -350, "y": 150, "category": "stand", "title": "Стенд 1"},
        {"x": 250, "y": 250, "category": "stand", "title": "Стенд 2"},
    ]

    nodes, edges = generate_auto_graph(1000, 800, layout, mock_pois)

    # Проверяем, что узлы в отрицательной зоне действительно имеют x < -50
    neg_nodes = [n for n in nodes if n["x"] < -50]
    assert len(neg_nodes) >= 5, "Узлы в отрицательной области не должны схлопываться или отсекаться!"

    # Узел POI должен быть в (-350, 150), а не прижат к 10
    poi_node = next(n for n in nodes if abs(n["x"] - (-350)) < 1.0 and abs(n["y"] - 150) < 1.0)
    assert poi_node is not None


def test_auto_graph_prevents_exterior_nodes_and_wall_clipping():
    """
    Проверяет, что при наличии комнат и коридора:
    1. Узлы не вылетают наружу здания в пустоту (за пределы комнат/коридоров).
    2. Ни одно ребро не режет внешние стены или углы стен.
    """
    layout = {
        "rooms": [
            {"id": "r1", "title": "ЗОНА 1", "x": 100, "y": 100, "width": 300, "height": 300},
            {"id": "r2", "title": "ЗОНА 2", "x": 600, "y": 100, "width": 300, "height": 300},
        ],
        "walls": [
            # Периметр Зоны 1
            {"x1": 100, "y1": 100, "x2": 400, "y2": 100},
            {"x1": 100, "y1": 400, "x2": 400, "y2": 400},
            {"x1": 100, "y1": 100, "x2": 100, "y2": 400},
            {"x1": 400, "y1": 100, "x2": 400, "y2": 220},  # дверной проём 220..280
            {"x1": 400, "y1": 280, "x2": 400, "y2": 400},
            # Периметр Зоны 2
            {"x1": 600, "y1": 100, "x2": 900, "y2": 100},
            {"x1": 600, "y1": 400, "x2": 900, "y2": 400},
            {"x1": 900, "y1": 100, "x2": 900, "y2": 400},
            {"x1": 600, "y1": 100, "x2": 600, "y2": 220},  # дверной проём 220..280
            {"x1": 600, "y1": 280, "x2": 600, "y2": 400},
        ],
        "corridors": [
            {"x1": 400, "y1": 250, "x2": 600, "y2": 250, "width": 40},
        ],
    }
    mock_pois = [
        {"x": 200, "y": 250, "category": "stand", "title": "st1"},
        {"x": 800, "y": 250, "category": "stand", "title": "st2"},
    ]

    nodes, edges = generate_auto_graph(1000, 600, layout, mock_pois)

    # 1. Проверяем, что нет узлов в пустоте (например, далеко над крышей y < 50 или под полом y > 450)
    void_nodes = [n for n in nodes if n["y"] < 50 or n["y"] > 450]
    assert len(void_nodes) == 0, f"Обнаружены узлы в пустоте за пределами здания: {void_nodes}"

    # 2. Проверяем, что в промежутке между комнатами (x от 420 до 580)
    # узлы могут находиться ТОЛЬКО вдоль коридора (y около 250), а не в пустоте вверху/внизу
    gap_void_nodes = [
        n for n in nodes
        if 420 < n["x"] < 580 and (n["y"] < 200 or n["y"] > 300)
    ]
    assert len(gap_void_nodes) == 0, f"Обнаружены узлы в пустоте между корпусами: {gap_void_nodes}"

    # 3. Ни одно ребро не должно пересекать стены
    from app.services.auto_graph import line_intersection
    for i1, i2 in edges:
        p1 = (nodes[i1]["x"], nodes[i1]["y"])
        p2 = (nodes[i2]["x"], nodes[i2]["y"])
        for w in layout["walls"]:
            w_p1 = (w["x1"], w["y1"])
            w_p2 = (w["x2"], w["y2"])
            assert not line_intersection(p1, p2, w_p1, w_p2), f"Ребро {p1}->{p2} режет стену {w}!"


def test_auto_graph_multi_room_segregation_and_no_direct_cuts():
    """
    Проверяет сценарий из баг-репорта с 11 комнатами:
    Маршрут между ЗОНА 3 и ЗОНА 8 не должен напрямую резать промежуточную ЗОНУ 4.
    В графе не должно быть прямых рёбер между разными комнатами без прохода через двери.
    """
    layout = {
        "rooms": [
            {"id": "r3", "title": "ЗОНА 3", "x": 50, "y": 200, "width": 200, "height": 150},
            {"id": "r4", "title": "ЗОНА 4", "x": 250, "y": 200, "width": 200, "height": 150},
            {"id": "r8", "title": "ЗОНА 8", "x": 450, "y": 200, "width": 200, "height": 150},
        ],
        "walls": [
            {"x1": 50, "y1": 200, "x2": 650, "y2": 200},
            {"x1": 650, "y1": 200, "x2": 650, "y2": 350},
            {"x1": 650, "y1": 350, "x2": 50, "y2": 350},
            {"x1": 50, "y1": 350, "x2": 50, "y2": 200},
            {"x1": 250, "y1": 200, "x2": 250, "y2": 260},
            {"x1": 250, "y1": 290, "x2": 250, "y2": 350},
            {"x1": 450, "y1": 200, "x2": 450, "y2": 260},
            {"x1": 450, "y1": 290, "x2": 450, "y2": 350},
        ],
        "corridors": [],
        "obstacles": [],
    }
    mock_pois = [
        {"x": 100, "y": 275, "category": "exhibit", "title": "Экспонат А"},
        {"x": 550, "y": 275, "category": "service", "title": "Стойка Б"},
    ]

    nodes, edges = generate_auto_graph(700, 700, layout, mock_pois)

    # 1. Проверяем, что нет узлов в пустоте
    for n in nodes:
        assert 50 <= n["x"] <= 650, f"Узел {n} за пределами здания по X!"
        assert 200 <= n["y"] <= 350, f"Узел {n} за пределами здания по Y!"

    # 2. Проверяем изоляцию комнат: ни одно ребро не связывает ЗОНА 3 и ЗОНА 8 напрямую
    for i1, i2 in edges:
        r1 = nodes[i1].get("room_id")
        r2 = nodes[i2].get("room_id")
        assert not (
            (r1 == "r3" and r2 == "r8") or (r1 == "r8" and r2 == "r3")
        ), f"Обнаружено прямое ребро между r3 и r8: {nodes[i1]} <-> {nodes[i2]}"

    # 3. Проверяем, что созданы дверные узлы на границах комнат (x=250 и x=450)
    door_nodes = [n for n in nodes if n["node_type"] == "door"]
    assert any(abs(n["x"] - 250.0) < 5.0 and abs(n["y"] - 275.0) < 5.0 for n in door_nodes), "Дверной проем между ЗОНА 3 и ЗОНА 4 не найден!"
    assert any(abs(n["x"] - 450.0) < 5.0 and abs(n["y"] - 275.0) < 5.0 for n in door_nodes), "Дверной проем между ЗОНА 4 и ЗОНА 8 не найден!"


def test_auto_graph_obstacle_clearance_and_zero_void_artifacts():
    """
    Проверяет сценарий из последнего баг-репорта:
    1. Препятствия, прилегающие к внешней стене (например, внизу здания),
       НЕ должны выталкивать узлы или рёбра в пустоту за пределы здания.
    2. Препятствия с отрицательными width/height не должны ломать расчет
       и не должны содержать узлов внутри себя.
    3. Внутри зон обеспечивается плотное равномерное покрытие сеткой (grid_step=45).
    4. Узлы не ставятся вплотную к стенам и препятствиям.
    """
    from app.services.auto_graph import distance_point_to_segment, normalize_rect

    layout = {
        "rooms": [
            {"id": "r9", "title": "ЗОНА 9", "x": 100, "y": 500, "width": 300, "height": 250},
            {"id": "r10", "title": "ЗОНА 10", "x": 400, "y": 500, "width": 300, "height": 250},
        ],
        "walls": [
            {"x1": 100, "y1": 500, "x2": 700, "y2": 500},
            {"x1": 100, "y1": 750, "x2": 700, "y2": 750},
            {"x1": 100, "y1": 500, "x2": 100, "y2": 750},
            {"x1": 700, "y1": 500, "x2": 700, "y2": 750},
            {"x1": 400, "y1": 500, "x2": 400, "y2": 600},
            {"x1": 400, "y1": 650, "x2": 400, "y2": 750},
        ],
        "obstacles": [
            # Препятствия, касающиеся нижней внешней стены (y=750)
            {"type": "rect", "x": 150, "y": 700, "width": 80, "height": 50},
            {"type": "rect", "x": 260, "y": 710, "width": 60, "height": 40},
            # Высокое препятствие внутри зоны 9
            {"type": "rect", "x": 120, "y": 530, "width": 50, "height": 120},
            # Препятствие с отрицательной шириной
            {"type": "rect", "x": 150, "y": 600, "width": -50, "height": 40},
        ],
        "corridors": [],
    }

    pois = [
        {"x": 130, "y": 720, "title": "POI 1", "category": "stand"},
        {"x": 600, "y": 600, "title": "POI 2", "category": "stand"},
    ]

    nodes, edges = generate_auto_graph(1000, 1000, layout, pois)

    # 1. Ноль узлов в пустоте за пределами здания
    void_nodes = [n for n in nodes if n["y"] > 750.5 or n["y"] < 499.5 or n["x"] < 99.5 or n["x"] > 700.5]
    assert len(void_nodes) == 0, f"Обнаружены узлы в пустоте за пределами здания: {void_nodes}"

    # 2. Ноль рёбер в пустоте за пределами здания
    for i1, i2 in edges:
        p1 = (nodes[i1]["x"], nodes[i1]["y"])
        p2 = (nodes[i2]["x"], nodes[i2]["y"])
        assert 499.5 <= p1[1] <= 750.5, f"Точка ребра {p1} в пустоте по Y!"
        assert 499.5 <= p2[1] <= 750.5, f"Точка ребра {p2} в пустоте по Y!"
        assert 99.5 <= p1[0] <= 700.5, f"Точка ребра {p1} в пустоте по X!"
        assert 99.5 <= p2[0] <= 700.5, f"Точка ребра {p2} в пустоте по X!"

    # 3. Ноль узлов внутри препятствий
    for n in nodes:
        for ob in layout["obstacles"]:
            rx, ry, rw, rh = normalize_rect(ob)
            inside = (rx <= n["x"] <= rx + rw and ry <= n["y"] <= ry + rh)
            assert not inside, f"Узел {n} находится внутри препятствия {ob}!"

    # 4. Узлы (кроме дверей) не лежат вплотную на стенах
    for n in nodes:
        if n["node_type"] != "door":
            for w in layout["walls"]:
                d = distance_point_to_segment(n["x"], n["y"], w["x1"], w["y1"], w["x2"], w["y2"])
                assert d >= 8.0, f"Узел {n} расположен слишком близко к стене {w} (d={d})!"

    # 5. Плотное покрытие: Зона 9 имеет более 20 узлов
    r9_nodes = [n for n in nodes if n.get("room_id") == "r9"]
    assert len(r9_nodes) >= 20, f"Покрытие Зоны 9 недостаточно плотное: {len(r9_nodes)} узлов"




