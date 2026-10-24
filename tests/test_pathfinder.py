"""
Юнит-тесты чистой навигационной математики (без БД):
геометрия проекций, веса рёбер, алгоритм A*.
"""

import uuid

import pytest

from app.services.pathfinder import (
    ELEVATOR_WEIGHT_METERS,
    STAIRS_WEIGHT_METERS,
    GraphEdge,
    GraphNode,
    astar,
    bearing_deg,
    build_adjacency,
    corridor_weight_meters,
    euclidean_px,
    find_nearest_edge_projection,
    find_nearest_node,
    project_point_on_segment,
    signed_turn_deg,
    turn_side,
)

PPM = 100.0  # 100 px = 1 м — удобно для проверок
FLOOR_1 = uuid.uuid4()
FLOOR_2 = uuid.uuid4()


def make_node(x, y, floor_id=FLOOR_1, floor_number=1, node_id=None) -> GraphNode:
    return GraphNode(
        id=node_id or uuid.uuid4(),
        floor_id=floor_id,
        x=x,
        y=y,
        ppm=PPM,
        floor_number=floor_number,
    )


def make_edge(a_id, b_id, kind="corridor", weight=1.0, accessible=True, bidirectional=True) -> GraphEdge:
    return GraphEdge(
        id=uuid.uuid4(),
        from_node_id=a_id,
        to_node_id=b_id,
        kind=kind,
        weight_meters=weight,
        is_accessible=accessible,
        bidirectional=bidirectional,
    )


# ---------------------------------------------------------------------------
# Базовая геометрия
# ---------------------------------------------------------------------------


def test_euclidean_px():
    assert euclidean_px(0, 0, 30, 40) == 50.0


def test_corridor_weight_uses_ppm():
    # 250 px при 100 px/м = 2.5 м
    assert corridor_weight_meters(0, 0, 250, 0, PPM) == 2.5
    with pytest.raises(ValueError):
        corridor_weight_meters(0, 0, 100, 0, 0)


def test_projection_onto_segment_middle():
    proj_x, proj_y, t, dist = project_point_on_segment(50, 30, 0, 0, 100, 0)
    assert (proj_x, proj_y) == (50, 0)
    assert t == 0.5
    assert dist == 30


def test_projection_clamped_to_endpoints():
    # За пределами отрезка — проекция прижимается к ближайшему концу
    _, _, t1, dist1 = project_point_on_segment(-40, 0, 0, 0, 100, 0)
    assert t1 == 0.0 and dist1 == 40
    _, _, t2, dist2 = project_point_on_segment(140, 0, 0, 0, 100, 0)
    assert t2 == 1.0 and dist2 == 40


def test_projection_degenerate_segment():
    proj_x, proj_y, t, dist = project_point_on_segment(3, 4, 0, 0, 0, 0)
    assert (proj_x, proj_y) == (0, 0)
    assert t == 0.0
    assert dist == 5.0


# ---------------------------------------------------------------------------
# Направления и стороны (ось Y направлена вниз!)
# ---------------------------------------------------------------------------


def test_bearing_cardinal_directions():
    assert bearing_deg(0, 0, 10, 0) == 0        # восток
    assert bearing_deg(0, 0, 0, 10) == 90       # юг (вниз по плану)
    assert bearing_deg(0, 0, 0, -10) == -90     # север (вверх по плану)
    assert abs(bearing_deg(0, 0, -10, 0)) == 180  # запад


def test_signed_turn_right_is_positive_in_image_coords():
    # Идём на восток, поворачиваем на юг — на экране это поворот НАПРАВО
    delta = signed_turn_deg(bearing_deg(0, 0, 10, 0), bearing_deg(10, 0, 10, 10))
    assert delta == 90
    # Идём на восток, поворачиваем на север — НАЛЕВО
    delta = signed_turn_deg(bearing_deg(0, 0, 10, 0), bearing_deg(10, 0, 10, -10))
    assert delta == -90


def test_turn_side_in_image_coords():
    # Идём на восток; точка к югу (внизу плана) — СПРАВА
    assert turn_side(0, 0, 10, 0, 5, 5) == "right"
    # Точка к северу — СЛЕВА
    assert turn_side(0, 0, 10, 0, 5, -5) == "left"


# ---------------------------------------------------------------------------
# Поиск ближайшего ребра / вершины
# ---------------------------------------------------------------------------


def test_find_nearest_edge_projection_picks_closest_segment():
    a = make_node(0, 0)
    b = make_node(100, 0)
    c = make_node(0, 200)
    d = make_node(100, 200)
    nodes = {n.id: n for n in (a, b, c, d)}
    e_top = make_edge(a.id, b.id)
    e_bottom = make_edge(c.id, d.id)

    proj = find_nearest_edge_projection(50, 60, FLOOR_1, nodes, [e_top, e_bottom])
    assert proj is not None
    assert proj.edge.id == e_top.id
    assert proj.distance_px == 60
    assert proj.t == 0.5


def test_find_nearest_edge_ignores_other_floors_and_kinds():
    a = make_node(0, 0)
    b = make_node(100, 0)
    g = make_node(0, 500, floor_id=FLOOR_2, floor_number=2)
    h = make_node(100, 500, floor_id=FLOOR_2, floor_number=2)
    nodes = {n.id: n for n in (a, b, g, h)}
    corridor = make_edge(a.id, b.id)
    stairs = make_edge(a.id, g.id, kind="stairs", weight=STAIRS_WEIGHT_METERS)
    other_floor = make_edge(g.id, h.id)

    proj = find_nearest_edge_projection(50, 10, FLOOR_1, nodes, [stairs, other_floor])
    assert proj is None  # коридорных рёбер на этаже нет

    proj = find_nearest_edge_projection(50, 10, FLOOR_1, nodes, [corridor, stairs, other_floor])
    assert proj is not None and proj.edge.id == corridor.id


def test_find_nearest_node_fallback():
    a = make_node(0, 0)
    b = make_node(100, 0)
    nodes = {a.id: a, b.id: b}
    node, dist = find_nearest_node(80, 0, FLOOR_1, nodes)
    assert node.id == b.id and dist == 20
    assert find_nearest_node(0, 0, FLOOR_2, nodes) is None


# ---------------------------------------------------------------------------
# A*
# ---------------------------------------------------------------------------


def build_simple_graph():
    """
    Линейка n1--n2--n3 с «дорогим» обходом n1--n4--n3:
    n1(0,0), n2(100,0), n3(200,0), n4(0,300).
    Веса: n1-n2 = 1м, n2-n3 = 1м, n1-n4 = 3м, n4-n3 = 3м.
    """
    n1, n2, n3, n4 = make_node(0, 0), make_node(100, 0), make_node(200, 0), make_node(0, 300)
    nodes = {n.id: n for n in (n1, n2, n3, n4)}
    edges = [
        make_edge(n1.id, n2.id, weight=1.0),
        make_edge(n2.id, n3.id, weight=1.0),
        make_edge(n1.id, n4.id, weight=3.0),
        make_edge(n4.id, n3.id, weight=3.0),
    ]
    return nodes, edges, (n1, n2, n3, n4)


def test_astar_finds_shortest_path():
    nodes, edges, (n1, n2, n3, _) = build_simple_graph()
    adjacency = build_adjacency(nodes, edges)
    result = astar(n1.id, {n3.id}, nodes, adjacency)
    assert result is not None
    assert result.node_ids == [n1.id, n2.id, n3.id]
    assert result.total_meters == 2.0
    assert len(result.edge_ids) == 2


def test_astar_multi_target_picks_nearest():
    nodes, edges, (n1, n2, n3, n4) = build_simple_graph()
    adjacency = build_adjacency(nodes, edges)
    result = astar(n1.id, {n3.id, n4.id}, nodes, adjacency)
    assert result is not None
    # До n4 — 3м напрямую, до n3 — 2м через n2: ближайшая цель — n3
    assert result.node_ids[-1] == n3.id


def test_astar_start_is_target():
    nodes, edges, (n1, _, _, _) = build_simple_graph()
    adjacency = build_adjacency(nodes, edges)
    result = astar(n1.id, {n1.id}, nodes, adjacency)
    assert result is not None and result.total_meters == 0.0


def test_astar_unreachable_returns_none():
    n1 = make_node(0, 0)
    n2 = make_node(100, 0)
    nodes = {n1.id: n1, n2.id: n2}
    adjacency = build_adjacency(nodes, [])
    assert astar(n1.id, {n2.id}, nodes, adjacency) is None


def test_astar_accessible_only_excludes_stairs():
    """
    Этаж 1: n1(0,0) --коридор--> s1(100,0)
    Этаж 2: s2(100,0) --коридор--> n2(200,0)
    Между s1 и s2 — лестница (недоступна). Другого пути нет.
    С доступным фильтром маршрута нет, без фильтра — есть.
    """
    n1 = make_node(0, 0)
    s1 = make_node(100, 0)
    s2 = make_node(100, 0, floor_id=FLOOR_2, floor_number=2)
    n2 = make_node(200, 0, floor_id=FLOOR_2, floor_number=2)
    nodes = {n.id: n for n in (n1, s1, s2, n2)}
    edges = [
        make_edge(n1.id, s1.id, weight=1.0),
        make_edge(s2.id, n2.id, weight=1.0),
        make_edge(s1.id, s2.id, kind="stairs", weight=STAIRS_WEIGHT_METERS, accessible=False),
    ]
    adjacency = build_adjacency(nodes, edges)

    assert astar(n1.id, {n2.id}, nodes, adjacency, accessible_only=True) is None
    result = astar(n1.id, {n2.id}, nodes, adjacency, accessible_only=False)
    assert result is not None
    assert result.total_meters == 1.0 + STAIRS_WEIGHT_METERS + 1.0


def test_astar_prefers_elevator_when_accessible():
    """Лифт (30м эквивалента) выигрывает у лестницы (35м) при прочих равных."""
    n1 = make_node(0, 0)
    s1 = make_node(100, 0)
    e1 = make_node(0, 100)
    s2 = make_node(100, 0, floor_id=FLOOR_2, floor_number=2)
    e2 = make_node(0, 100, floor_id=FLOOR_2, floor_number=2)
    n2 = make_node(200, 0, floor_id=FLOOR_2, floor_number=2)
    nodes = {n.id: n for n in (n1, s1, e1, s2, e2, n2)}
    edges = [
        make_edge(n1.id, s1.id, weight=1.0),
        make_edge(n1.id, e1.id, weight=1.0),
        make_edge(s2.id, n2.id, weight=1.0),
        make_edge(e2.id, n2.id, weight=1.0),
        make_edge(s1.id, s2.id, kind="stairs", weight=STAIRS_WEIGHT_METERS, accessible=False),
        make_edge(e1.id, e2.id, kind="elevator", weight=ELEVATOR_WEIGHT_METERS),
    ]
    adjacency = build_adjacency(nodes, edges)
    result = astar(n1.id, {n2.id}, nodes, adjacency, accessible_only=True)
    assert result is not None
    assert result.node_ids == [n1.id, e1.id, e2.id, n2.id]
    assert result.total_meters == 1.0 + ELEVATOR_WEIGHT_METERS + 1.0


def test_astar_respects_one_way_edges():
    n1, n2 = make_node(0, 0), make_node(100, 0)
    nodes = {n1.id: n1, n2.id: n2}
    one_way = make_edge(n1.id, n2.id, bidirectional=False)
    adjacency = build_adjacency(nodes, [one_way])
    # В прямую сторону путь есть, в обратную — нет
    assert astar(n1.id, {n2.id}, nodes, adjacency) is not None
    assert astar(n2.id, {n1.id}, nodes, adjacency) is None
