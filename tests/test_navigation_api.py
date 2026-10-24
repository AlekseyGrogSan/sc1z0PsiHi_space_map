"""
Интеграционные тесты API навигации: редактирование графа организатором,
межэтажные переходы (лестницы/лифты) и построение маршрута для посетителя.
"""

import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.floor import Floor
from app.models.panorama import Panorama
from app.models.poi import POI, POICategory
from app.models.space import Space, SpaceMember, SpaceRole
from app.models.user import SystemRole, User
from app.core.security import hash_password

PPM = 100.0  # 100 px = 1 м


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture
async def nav_world(db_session: AsyncSession, organizer_user: User):
    """Пространство с двумя этажами (ppm задан) и владельцем-организатором."""
    space = Space(title="Экспо-центр", slug="expo-nav", is_published=True)
    db_session.add(space)
    await db_session.flush()  # id пространства генерируется только при вставке
    db_session.add(
        SpaceMember(space_id=space.id, user_id=organizer_user.id, role=SpaceRole.OWNER)
    )
    floor1 = Floor(
        space_id=space.id, floor_number=1, title="1 этаж",
        ppm=PPM, width_px=1000, height_px=800,
    )
    floor2 = Floor(
        space_id=space.id, floor_number=2, title="2 этаж",
        ppm=PPM, width_px=1000, height_px=800,
    )
    db_session.add_all([floor1, floor2])
    await db_session.commit()
    for obj in (space, floor1, floor2):
        await db_session.refresh(obj)
    return SimpleNamespace(space=space, floor1=floor1, floor2=floor2)


@pytest.fixture
async def stranger_headers(db_session: AsyncSession) -> dict:
    """Пользователь, не входящий в команду пространства."""
    user = User(
        email="stranger@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Stranger",
        system_role=SystemRole.ORGANIZER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def graph_url(floor_id) -> str:
    return f"/api/v1/floors/{floor_id}/navigation/graph"


def transitions_url(space_id) -> str:
    return f"/api/v1/spaces/{space_id}/navigation/transitions"


def route_url(space_id) -> str:
    return f"/api/v1/spaces/{space_id}/navigation/route"


async def put_graph(client: AsyncClient, floor_id, nodes, edges, headers) -> dict:
    """nodes: [(ref, x, y)], edges: [(from_ref, to_ref)] -> ответ PUT."""
    resp = await client.put(
        graph_url(floor_id),
        json={
            "nodes": [{"ref": r, "x": x, "y": y} for r, x, y in nodes],
            "edges": [{"from_ref": a, "to_ref": b} for a, b in edges],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def id_map(saved: dict) -> dict:
    """ref -> uuid из ответа пакетного сохранения."""
    return saved["node_id_map"]


async def make_poi(db_session: AsyncSession, floor_id, title, x, y) -> POI:
    poi = POI(
        floor_id=floor_id, title=title, category=POICategory.STAND,
        x_coord=x, y_coord=y,
    )
    db_session.add(poi)
    await db_session.commit()
    await db_session.refresh(poi)
    return poi


@pytest.fixture
async def two_floor_graph(client: AsyncClient, nav_world, auth_headers, db_session):
    """
    Этаж 1: n1(0,0)—n2(100,0)—n3(200,0)—s1(200,50)
    Этаж 2: s2(200,50)—m1(100,50)
    Лестница: s1—s2. POI «Стенд ТТК» на этаже 2 в (90,50).
    """
    w = nav_world
    g1 = await put_graph(
        client, w.floor1.id,
        [("n1", 0, 0), ("n2", 100, 0), ("n3", 200, 0), ("s1", 200, 50)],
        [("n1", "n2"), ("n2", "n3"), ("n3", "s1")],
        auth_headers,
    )
    g2 = await put_graph(
        client, w.floor2.id,
        [("s2", 200, 50), ("m1", 100, 50)],
        [("s2", "m1")],
        auth_headers,
    )
    ids = {**id_map(g1), **id_map(g2)}
    resp = await client.post(
        transitions_url(w.space.id),
        json={"from_node_id": ids["s1"], "to_node_id": ids["s2"], "kind": "stairs"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    poi = await make_poi(db_session, w.floor2.id, "Стенд ТТК", 90, 50)
    return SimpleNamespace(ids=ids, poi=poi, transition=resp.json())


# ---------------------------------------------------------------------------
# Редактирование графа этажа
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_and_get_floor_graph(client: AsyncClient, nav_world, auth_headers):
    floor_id = nav_world.floor1.id
    saved = await put_graph(
        client, floor_id,
        [("a", 0, 0), ("b", 100, 0), ("c", 200, 0)],
        [("a", "b"), ("b", "c")],
        auth_headers,
    )
    assert set(saved["node_id_map"].keys()) == {"a", "b", "c"}

    # Веса посчитаны на сервере: 100 px / 100 ppm = 1 м
    weights = sorted(e["weight_meters"] for e in saved["graph"]["edges"])
    assert weights == [1.0, 1.0]
    assert all(e["kind"] == "corridor" for e in saved["graph"]["edges"])
    assert all(e["is_accessible"] and e["bidirectional"] for e in saved["graph"]["edges"])

    # Публичное чтение графа — без авторизации
    resp = await client.get(graph_url(floor_id))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2


@pytest.mark.asyncio
async def test_put_graph_replaces_previous_content(client: AsyncClient, nav_world, auth_headers):
    floor_id = nav_world.floor1.id
    first = await put_graph(
        client, floor_id,
        [("a", 0, 0), ("b", 100, 0), ("c", 200, 0)],
        [("a", "b"), ("b", "c")],
        auth_headers,
    )
    keep_id = first["node_id_map"]["a"]

    # Второй PUT: вершина a сохраняется по id, b и c удаляются, d — новая
    resp = await client.put(
        graph_url(floor_id),
        json={
            "nodes": [
                {"ref": "a", "id": keep_id, "x": 0, "y": 0},
                {"ref": "d", "x": 0, "y": 100},
            ],
            "edges": [{"from_ref": "a", "to_ref": "d"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["node_id_map"]["a"] == keep_id

    graph = data["graph"]
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["weight_meters"] == 1.0
    remaining_ids = {n["id"] for n in graph["nodes"]}
    assert keep_id in remaining_ids


@pytest.mark.asyncio
async def test_put_graph_auth_required(client: AsyncClient, nav_world, stranger_headers):
    body = {"nodes": [{"ref": "a", "x": 0, "y": 0}], "edges": []}
    # Без токена — 401
    resp = await client.put(graph_url(nav_world.floor1.id), json=body)
    assert resp.status_code == 401
    # Чужой пользователь — 403
    resp = await client.put(
        graph_url(nav_world.floor1.id), json=body, headers=stranger_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_graph_validation_errors(client: AsyncClient, nav_world, auth_headers):
    floor_id = nav_world.floor1.id

    # Ребро ссылается на неизвестный ref
    resp = await client.put(
        graph_url(floor_id),
        json={
            "nodes": [{"ref": "a", "x": 0, "y": 0}],
            "edges": [{"from_ref": "a", "to_ref": "ghost"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # Дублирующиеся ref вершин
    resp = await client.put(
        graph_url(floor_id),
        json={
            "nodes": [{"ref": "a", "x": 0, "y": 0}, {"ref": "a", "x": 1, "y": 1}],
            "edges": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # Дублирующееся ребро (в т.ч. в обратную сторону)
    resp = await client.put(
        graph_url(floor_id),
        json={
            "nodes": [{"ref": "a", "x": 0, "y": 0}, {"ref": "b", "x": 100, "y": 0}],
            "edges": [
                {"from_ref": "a", "to_ref": "b"},
                {"from_ref": "b", "to_ref": "a"},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422

    # Петля (ребро в себя)
    resp = await client.put(
        graph_url(floor_id),
        json={
            "nodes": [{"ref": "a", "x": 0, "y": 0}],
            "edges": [{"from_ref": "a", "to_ref": "a"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_graph_rejects_foreign_node_id(client: AsyncClient, nav_world, auth_headers):
    other = await put_graph(
        client, nav_world.floor2.id, [("x", 0, 0)], [], auth_headers
    )
    foreign_id = other["node_id_map"]["x"]
    resp = await client.put(
        graph_url(nav_world.floor1.id),
        json={"nodes": [{"ref": "a", "id": foreign_id, "x": 0, "y": 0}], "edges": []},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "does not belong" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_put_graph_requires_ppm(client: AsyncClient, nav_world, auth_headers, db_session):
    floor = Floor(space_id=nav_world.space.id, floor_number=3, title="3 этаж")
    db_session.add(floor)
    await db_session.commit()
    resp = await client.put(
        graph_url(floor.id),
        json={
            "nodes": [{"ref": "a", "x": 0, "y": 0}, {"ref": "b", "x": 1, "y": 0}],
            "edges": [{"from_ref": "a", "to_ref": "b"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    await db_session.refresh(floor)
    assert floor.ppm == 25.0


# ---------------------------------------------------------------------------
# Межэтажные переходы
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_crud_and_validation(client: AsyncClient, nav_world, auth_headers):
    w = nav_world
    g1 = await put_graph(client, w.floor1.id, [("s1", 10, 10), ("w1", 0, 0)], [("s1", "w1")], auth_headers)
    g2 = await put_graph(client, w.floor2.id, [("s2", 10, 10)], [], auth_headers)
    s1, s2, w1 = g1["node_id_map"]["s1"], g2["node_id_map"]["s2"], g1["node_id_map"]["w1"]

    # Лестница между этажами — ок
    resp = await client.post(
        transitions_url(w.space.id),
        json={"from_node_id": s1, "to_node_id": s2, "kind": "stairs"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    transition = resp.json()
    assert transition["kind"] == "stairs"
    assert transition["weight_meters"] == 35.0  # вес лестницы = 35 м эквивалента
    assert transition["is_accessible"] is False
    assert transition["from_endpoint"]["floor_number"] == 1
    assert transition["to_endpoint"]["floor_number"] == 2

    # Вершины пометились типом stairs
    graph1 = (await client.get(graph_url(w.floor1.id))).json()
    node_types = {n["id"]: n["node_type"] for n in graph1["nodes"]}
    assert node_types[s1] == "stairs"
    assert node_types[w1] == "walkway"

    # Дубликат — 409
    resp = await client.post(
        transitions_url(w.space.id),
        json={"from_node_id": s2, "to_node_id": s1, "kind": "elevator"},
        headers=auth_headers,
    )
    assert resp.status_code == 409

    # Между вершинами одного этажа — 400
    # Сохраняем s1 с его текущим ID, чтобы не сломать stairs-переход
    resp = await client.put(
        graph_url(w.floor1.id),
        json={
            "nodes": [
                {"ref": "_s1", "id": s1, "x": 10, "y": 10},
                {"ref": "_w1", "id": w1, "x": 0, "y": 0},
                {"ref": "w2", "x": 500, "y": 0},
            ],
            "edges": [{"from_ref": "_s1", "to_ref": "_w1"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    w2_id = resp.json()["node_id_map"]["w2"]
    resp = await client.post(
        transitions_url(w.space.id),
        json={"from_node_id": w1, "to_node_id": w2_id, "kind": "stairs"},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # kind=corridor — 400
    resp = await client.post(
        transitions_url(w.space.id),
        json={"from_node_id": s1, "to_node_id": s2, "kind": "corridor"},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # Публичный список переходов
    resp = await client.get(transitions_url(w.space.id))
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Удаление (owner) и пустой список после
    resp = await client.delete(
        f"{transitions_url(w.space.id)}/{transition['id']}", headers=auth_headers
    )
    assert resp.status_code == 204
    resp = await client.get(transitions_url(w.space.id))
    assert resp.json() == []

    # Повторное удаление — 404
    resp = await client.delete(
        f"{transitions_url(w.space.id)}/{transition['id']}", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transition_node_from_other_space_rejected(
    client: AsyncClient, nav_world, auth_headers, db_session, superadmin_headers
):
    # Граф в нашем пространстве
    g1 = await put_graph(client, nav_world.floor1.id, [("a", 0, 0)], [], auth_headers)
    node_a = g1["node_id_map"]["a"]

    # Чужое пространство и граф в нём (создаёт суперадмин — ему можно всё)
    other_space = Space(title="Чужое", slug="alien", is_published=True)
    db_session.add(other_space)
    await db_session.flush()
    other_floor = Floor(space_id=other_space.id, floor_number=9, title="9 этаж", ppm=PPM)
    db_session.add(other_floor)
    await db_session.commit()
    await db_session.refresh(other_floor)
    g2 = await put_graph(client, other_floor.id, [("b", 0, 0)], [], superadmin_headers)
    node_b = g2["node_id_map"]["b"]

    resp = await client.post(
        transitions_url(nav_world.space.id),
        json={"from_node_id": node_a, "to_node_id": node_b, "kind": "elevator"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "this space" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_put_graph_cannot_delete_node_used_by_transition(
    client: AsyncClient, two_floor_graph, nav_world, auth_headers
):
    ids = two_floor_graph.ids
    # Пытаемся перезаписать граф этажа 1 БЕЗ вершины s1 (на ней лестница) — 409
    resp = await client.put(
        graph_url(nav_world.floor1.id),
        json={
            "nodes": [
                {"ref": "n1", "id": ids["n1"], "x": 0, "y": 0},
                {"ref": "n2", "id": ids["n2"], "x": 100, "y": 0},
            ],
            "edges": [{"from_ref": "n1", "to_ref": "n2"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert ids["s1"] in resp.json()["detail"]

    # А с сохранением s1 — успешно
    resp = await client.put(
        graph_url(nav_world.floor1.id),
        json={
            "nodes": [
                {"ref": "n1", "id": ids["n1"], "x": 0, "y": 0},
                {"ref": "s1", "id": ids["s1"], "x": 200, "y": 50},
            ],
            "edges": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Маршрутизация
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_same_floor_with_projection(client: AsyncClient, nav_world, auth_headers, db_session):
    """
    Точка А не совпадает с вершиной: A=(30,150) проецируется на ребро
    n1(0,0)—n2(100,0). Маршрут стартует от ближайшей по стоимости вершины
    (n2), инструкция начинается с подхода к ней.
    """
    w = nav_world
    g = await put_graph(
        client, w.floor1.id,
        [("n1", 0, 0), ("n2", 100, 0), ("n3", 200, 0)],
        [("n1", "n2"), ("n2", "n3")],
        auth_headers,
    )
    ids = id_map(g)
    poi = await make_poi(db_session, w.floor1.id, "Гардероб", 200, 10)

    resp = await client.post(
        route_url(w.space.id),
        json={"floor_id": str(w.floor1.id), "x": 30, "y": 150, "to_poi_id": str(poi.id)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Вход: проекция на ребро n1-n2 (t=0.3 < 0.4), стартовая вершина — n1
    assert data["entry"]["projected_point"] == {"x": 30.0, "y": 0.0, "floor_id": str(w.floor1.id)}
    assert data["entry"]["node_id"] == ids["n1"]
    assert data["entry"]["walk_distance_meters"] == pytest.approx(1.5, abs=0.1)

    # Путь: n1 -> n2 -> n3, три шага: подход + прямо + прибытие
    assert [n["id"] for n in data["nodes"]] == [ids["n1"], ids["n2"], ids["n3"]]
    assert len(data["edges"]) == 2
    step_kinds = [s["kind"] for s in data["steps"]]
    assert step_kinds[0] == "approach"
    assert "walk" in step_kinds
    assert data["steps"][-1]["kind"] == "arrival"
    assert "Гардероб" in data["steps"][-1]["text"]

    # Полная дистанция: ~1.53 (подход) + 2.0 (граф) + 0.1 (сход) ≈ 3.6 м
    assert data["total_distance_meters"] == pytest.approx(3.6, abs=0.2)
    assert data["estimated_time_seconds"] >= 1


@pytest.mark.asyncio
async def test_route_across_floors_via_stairs(client: AsyncClient, nav_world, two_floor_graph):
    w = nav_world
    ids = two_floor_graph.ids

    resp = await client.post(
        route_url(w.space.id),
        json={
            "floor_id": str(w.floor1.id), "x": 5, "y": 0,
            "to_poi_id": str(two_floor_graph.poi.id),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Маршрут проходит через лестницу s1->s2
    edge_kinds = [e["kind"] for e in data["edges"]]
    assert "stairs" in edge_kinds
    floors_on_path = {n["floor_number"] for n in data["nodes"]}
    assert floors_on_path == {1, 2}
    assert [n["id"] for n in data["nodes"]] == [
        ids["n1"], ids["n2"], ids["n3"], ids["s1"], ids["s2"], ids["m1"]
    ]

    # Дистанция: ~0.05 подход + 2.5 по 1-му этажу + 35 лестница + 1.0 + 0.1 сход
    assert data["total_distance_meters"] == pytest.approx(38.6, abs=0.3)

    # Инструкция: есть поворот направо у n3 и подъём по лестнице на 2 этаж
    texts = [s["text"] for s in data["steps"]]
    assert "Поверните направо" in texts
    assert any("по лестнице на 2 этаж" in t for t in texts)
    assert "Стенд ТТК" in data["steps"][-1]["text"]


@pytest.mark.asyncio
async def test_route_wheelchair_accessible_uses_elevator(
    client: AsyncClient, nav_world, two_floor_graph, auth_headers
):
    w = nav_world
    ids = two_floor_graph.ids

    # Без лифта доступного маршрута нет — лестница исключена
    resp = await client.post(
        route_url(w.space.id),
        json={
            "floor_id": str(w.floor1.id), "x": 5, "y": 0,
            "to_poi_id": str(two_floor_graph.poi.id),
            "wheelchair_accessible_only": True,
        },
    )
    assert resp.status_code == 404
    assert "без лестниц" in resp.json()["detail"]

    # Добавляем лифт e1(0,600) [эт.1] — e2(0,600) [эт.2] вдали от лестницы
    g1 = await client.get(graph_url(w.floor1.id))
    nodes1 = g1.json()["nodes"]
    payload_nodes = [
        {"ref": n["id"], "id": n["id"], "x": n["x"], "y": n["y"], "node_type": n["node_type"]}
        for n in nodes1
    ]
    payload_nodes.append({"ref": "e1", "x": 0, "y": 600})
    # восстанавливаем существующие коридорные рёбра по координатам
    by_xy = {(n["x"], n["y"]): n["id"] for n in nodes1}
    payload_edges = [
        {"from_ref": by_xy[(0.0, 0.0)], "to_ref": by_xy[(100.0, 0.0)]},
        {"from_ref": by_xy[(100.0, 0.0)], "to_ref": by_xy[(200.0, 0.0)]},
        {"from_ref": by_xy[(200.0, 0.0)], "to_ref": by_xy[(200.0, 50.0)]},
        {"from_ref": by_xy[(0.0, 0.0)], "to_ref": "e1"},
    ]
    resp = await client.put(
        graph_url(w.floor1.id),
        json={"nodes": payload_nodes, "edges": payload_edges},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    e1 = resp.json()["node_id_map"]["e1"]

    g2 = await client.get(graph_url(w.floor2.id))
    nodes2 = g2.json()["nodes"]
    by_xy2 = {(n["x"], n["y"]): n["id"] for n in nodes2}
    resp = await client.put(
        graph_url(w.floor2.id),
        json={
            "nodes": [
                {"ref": n["id"], "id": n["id"], "x": n["x"], "y": n["y"], "node_type": n["node_type"]}
                for n in nodes2
            ]
            + [{"ref": "e2", "x": 0, "y": 600}],
            "edges": [
                {"from_ref": by_xy2[(200.0, 50.0)], "to_ref": by_xy2[(100.0, 50.0)]},
                {"from_ref": by_xy2[(100.0, 50.0)], "to_ref": "e2"},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    e2 = resp.json()["node_id_map"]["e2"]

    resp = await client.post(
        transitions_url(w.space.id),
        json={"from_node_id": e1, "to_node_id": e2, "kind": "elevator"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["weight_meters"] == 30.0
    assert resp.json()["is_accessible"] is True

    # Доступный маршрут теперь идёт через лифт
    resp = await client.post(
        route_url(w.space.id),
        json={
            "floor_id": str(w.floor1.id), "x": 5, "y": 0,
            "to_poi_id": str(two_floor_graph.poi.id),
            "wheelchair_accessible_only": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    edge_kinds = [e["kind"] for e in data["edges"]]
    assert "elevator" in edge_kinds
    assert "stairs" not in edge_kinds
    assert any("на лифте на 2 этаж" in s["text"] for s in data["steps"])

    # Обычный маршрут по-прежнему выбирает более короткую лестницу
    resp = await client.post(
        route_url(w.space.id),
        json={
            "floor_id": str(w.floor1.id), "x": 5, "y": 0,
            "to_poi_id": str(two_floor_graph.poi.id),
        },
    )
    assert resp.status_code == 200
    assert "stairs" in [e["kind"] for e in resp.json()["edges"]]


@pytest.mark.asyncio
async def test_route_direct_walk_along_same_edge(client: AsyncClient, nav_world, auth_headers, db_session):
    """А и POI проецируются на одно ребро — идём вдоль него без вершин."""
    w = nav_world
    await put_graph(
        client, w.floor1.id,
        [("n1", 0, 0), ("n2", 100, 0)],
        [("n1", "n2")],
        auth_headers,
    )
    poi = await make_poi(db_session, w.floor1.id, "Wi-Fi зона", 70, 5)

    resp = await client.post(
        route_url(w.space.id),
        json={"floor_id": str(w.floor1.id), "x": 30, "y": 0, "to_poi_id": str(poi.id)},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["nodes"] == []  # вершины не проходим
    assert len(data["edges"]) == 1
    assert data["total_distance_meters"] < 1.0
    assert len(data["steps"]) == 1
    assert "Wi-Fi зона" in data["steps"][0]["text"]


@pytest.mark.asyncio
async def test_route_returns_panoramas_along_path(
    client: AsyncClient, nav_world, auth_headers, db_session
):
    w = nav_world
    pano = Panorama(
        floor_id=w.floor1.id, title="Холл", x_coord=100, y_coord=0,
        status="ready",
    )
    db_session.add(pano)
    await db_session.commit()
    await db_session.refresh(pano)

    resp = await client.put(
        graph_url(w.floor1.id),
        json={
            "nodes": [
                {"ref": "n1", "x": 0, "y": 0},
                {"ref": "n2", "x": 100, "y": 0, "panorama_id": str(pano.id)},
                {"ref": "n3", "x": 200, "y": 0},
            ],
            "edges": [{"from_ref": "n1", "to_ref": "n2"}, {"from_ref": "n2", "to_ref": "n3"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    poi = await make_poi(db_session, w.floor1.id, "Кафе", 200, 0)
    resp = await client.post(
        route_url(w.space.id),
        json={"floor_id": str(w.floor1.id), "x": 0, "y": 0, "to_poi_id": str(poi.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["panorama_ids"] == [str(pano.id)]


@pytest.mark.asyncio
async def test_route_panorama_binding_validated(client: AsyncClient, nav_world, auth_headers, db_session):
    w = nav_world
    alien_pano = Panorama(floor_id=w.floor2.id, title="Чужая", x_coord=0, y_coord=0, status="ready")
    db_session.add(alien_pano)
    await db_session.commit()
    await db_session.refresh(alien_pano)

    resp = await client.put(
        graph_url(w.floor1.id),
        json={
            "nodes": [{"ref": "n1", "x": 0, "y": 0, "panorama_id": str(alien_pano.id)}],
            "edges": [],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "different floor" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_route_error_cases(client: AsyncClient, nav_world, auth_headers, db_session):
    w = nav_world
    g = await put_graph(client, w.floor1.id, [("n1", 0, 0), ("n2", 100, 0)], [("n1", "n2")], auth_headers)
    poi = await make_poi(db_session, w.floor1.id, "Стойка информации", 100, 0)

    # Несуществующее пространство
    resp = await client.post(
        route_url(uuid.uuid4()),
        json={"floor_id": str(w.floor1.id), "x": 0, "y": 0, "to_poi_id": str(poi.id)},
    )
    assert resp.status_code == 404

    # Несуществующая POI
    resp = await client.post(
        route_url(w.space.id),
        json={"floor_id": str(w.floor1.id), "x": 0, "y": 0, "to_poi_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404

    # POI из чужого пространства
    other_space = Space(title="Чужое", slug="alien-2", is_published=True)
    db_session.add(other_space)
    await db_session.flush()
    other_floor = Floor(space_id=other_space.id, floor_number=1, title="1", ppm=PPM)
    db_session.add(other_floor)
    await db_session.commit()
    await db_session.refresh(other_floor)
    alien_poi = await make_poi(db_session, other_floor.id, "Чужой стенд", 0, 0)
    resp = await client.post(
        route_url(w.space.id),
        json={"floor_id": str(w.floor1.id), "x": 0, "y": 0, "to_poi_id": str(alien_poi.id)},
    )
    assert resp.status_code == 404

    # Этаж без графа (2 этаж пуст)
    resp = await client.post(
        route_url(w.space.id),
        json={"floor_id": str(w.floor2.id), "x": 0, "y": 0, "to_poi_id": str(poi.id)},
    )
    assert resp.status_code == 422

    # Этаж без масштаба ppm
    floor3 = Floor(space_id=w.space.id, floor_number=3, title="3 этаж")
    db_session.add(floor3)
    await db_session.commit()
    resp = await client.post(
        route_url(w.space.id),
        json={"floor_id": str(floor3.id), "x": 0, "y": 0, "to_poi_id": str(poi.id)},
    )
    assert resp.status_code == 422
    assert "ppm" in resp.json()["detail"]
