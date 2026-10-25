"""
Оркестрация построения пешеходного маршрута: от произвольной точки «А»
до точки интереса (POI) по навигационному графу пространства.

Алгоритм:
1. Точка «А» проецируется на ближайшее коридорное ребро своего этажа
   (расстояние от точки до отрезка); кандидатами на старт становятся обе
   вершины этого ребра. Аналогично ищется сход к POI на её этаже.
2. A* запускается от каждого стартового кандидата до ближайшего
   целевого; выбирается вариант с минимальной полной стоимостью
   (подход пешком + путь по графу + сход к POI). Отдельно проверяется
   вырожденный случай «А и POI проецируются на одно и то же ребро».
3. По найденной цепочке вершин строятся «ноги» маршрута и человеко-
   понятная инструкция (app/services/route_instructions.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.floor import Floor
from app.models.navigation import NavEdgeKind, NavNodeType
from app.models.poi import POI
from app.models.space import Space
from app.repositories.navigation_repository import navigation_repo
from app.repositories.poi_repository import poi_repo
from app.schemas.navigation import (
    RouteEndpointInfo,
    RoutePathEdgeRead,
    RoutePathNodeRead,
    RoutePointRead,
    RouteRequest,
    RouteResponse,
    RouteStepRead,
)
from app.services import route_instructions as instr
from app.services.pathfinder import (
    WALKING_SPEED_MPS,
    EdgeProjection,
    GraphEdge,
    GraphNode,
    astar,
    bearing_deg,
    build_adjacency,
    euclidean_px,
    find_nearest_edge_projection,
    find_nearest_node,
)


class RoutingError(Exception):
    """Ошибка построения маршрута, мапится в HTTP-ответ слоем API."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class _GraphContext:
    """Подготовленный для расчётов граф пространства."""

    floors: Dict[uuid.UUID, Floor]
    nodes: Dict[uuid.UUID, GraphNode]
    edges: Dict[uuid.UUID, GraphEdge]
    adjacency: Dict[uuid.UUID, List[Tuple[uuid.UUID, GraphEdge]]]


@dataclass
class _Candidate:
    """Один оценённый вариант маршрута."""

    total_meters: float
    start_node_id: Optional[uuid.UUID]  # None — прямой проход вдоль ребра
    end_node_id: Optional[uuid.UUID]
    path_node_ids: List[uuid.UUID]
    path_edge_ids: List[uuid.UUID]
    approach_meters: float  # пешком от А до стартовой вершины
    exit_meters: float  # пешком от конечной вершины до POI


def _build_context(
    floors: Sequence[Floor],
    nodes_db: Sequence,
    edges_db: Sequence,
) -> _GraphContext:
    floor_map = {f.id: f for f in floors}
    nodes: Dict[uuid.UUID, GraphNode] = {}
    for n in nodes_db:
        floor = floor_map[n.floor_id]
        nodes[n.id] = GraphNode(
            id=n.id,
            floor_id=n.floor_id,
            x=n.x,
            y=n.y,
            ppm=floor.ppm or 0.0,
            floor_number=floor.floor_number,
            node_type=n.node_type.value if isinstance(n.node_type, NavNodeType) else n.node_type,
            panorama_id=n.panorama_id,
        )
    edges: Dict[uuid.UUID, GraphEdge] = {
        e.id: GraphEdge(
            id=e.id,
            from_node_id=e.from_node_id,
            to_node_id=e.to_node_id,
            kind=e.kind.value if isinstance(e.kind, NavEdgeKind) else e.kind,
            weight_meters=e.weight_meters,
            is_accessible=e.is_accessible,
            bidirectional=e.bidirectional,
        )
        for e in edges_db
    }
    return _GraphContext(
        floors=floor_map,
        nodes=nodes,
        edges=edges,
        adjacency=build_adjacency(nodes, edges.values()),
    )


def _floor_or_error(ctx: _GraphContext, floor_id: uuid.UUID, what: str) -> Floor:
    floor = ctx.floors.get(floor_id)
    if floor is None:
        raise RoutingError(f"{what} не найден в этом пространстве", status_code=404)
    if not floor.ppm or floor.ppm <= 0:
        raise RoutingError(
            f"Для этажа «{floor.title}» не задан масштаб ppm — маршрут невозможен",
            status_code=422,
        )
    return floor


from app.services.auto_graph import find_room_for_point, is_point_navigable, is_segment_clear, is_segment_walkable
from app.services.pathfinder import (
    WALKING_SPEED_MPS,
    EdgeProjection,
    GraphEdge,
    GraphNode,
    astar,
    bearing_deg,
    build_adjacency,
    euclidean_px,
    find_candidate_edge_projections,
    find_nearest_edge_projection,
    find_nearest_node,
)


def _snap_to_navigable(
    x: float,
    y: float,
    walls: List[Dict[str, float]],
    circle_obstacles: List[Dict[str, float]],
    rect_obstacles: List[Dict[str, float]],
    rooms: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[float, float]:
    """Если точка лежит внутри препятствия или стены, сдвигает её в ближайшую проходимую зону."""
    if not (walls or circle_obstacles or rect_obstacles):
        return x, y
    if is_point_navigable(x, y, walls, circle_obstacles, rect_obstacles, min_wall_dist=3.0, min_obstacle_dist=3.0):
        return x, y

    cur_room = find_room_for_point(x, y, rooms or [], tolerance=5.0)

    # Ищем в радиусе до 80px с нарастающим шагом
    for r in [4.0, 8.0, 14.0, 22.0, 32.0, 45.0, 60.0, 80.0]:
        for k in range(16):
            angle = k * (2.0 * math.pi / 16.0)
            cx = x + r * math.cos(angle)
            cy = y + r * math.sin(angle)
            if cur_room and find_room_for_point(cx, cy, rooms or [], tolerance=2.0) != cur_room:
                continue
            if is_point_navigable(cx, cy, walls, circle_obstacles, rect_obstacles, min_wall_dist=3.0, min_obstacle_dist=3.0):
                return cx, cy

    return x, y


def _get_floor_navigable_bounds(floor: Floor) -> Tuple[float, float, float, float]:
    """Вычисляет общие охватывающие границы (min_x, min_y, max_x, max_y) этажа."""
    layout = floor.layout_data or {}
    rooms = layout.get("rooms", [])
    walls = layout.get("walls", [])
    corridors = layout.get("corridors", [])
    obstacles = layout.get("obstacles", [])

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for r in rooms:
        pts = r.get("points")
        if pts and isinstance(pts, list):
            for pt in pts:
                try:
                    px, py = float(pt[0]), float(pt[1])
                    min_x = min(min_x, px)
                    max_x = max(max_x, px)
                    min_y = min(min_y, py)
                    max_y = max(max_y, py)
                except (ValueError, TypeError, IndexError):
                    pass
        elif "x" in r and "y" in r:
            rx, ry = float(r["x"]), float(r["y"])
            rw, rh = float(r.get("width", 0)), float(r.get("height", 0))
            min_x = min(min_x, rx)
            max_x = max(max_x, rx + rw)
            min_y = min(min_y, ry)
            max_y = max(max_y, ry + rh)

    for w in walls:
        try:
            x1, y1 = float(w.get("x1", 0)), float(w.get("y1", 0))
            x2, y2 = float(w.get("x2", 0)), float(w.get("y2", 0))
            min_x = min(min_x, x1, x2)
            max_x = max(max_x, x1, x2)
            min_y = min(min_y, y1, y2)
            max_y = max(max_y, y1, y2)
        except (ValueError, TypeError):
            pass

    for c in corridors:
        try:
            hw = float(c.get("width", 35)) / 2.0
            x1, y1 = float(c.get("x1", 0)), float(c.get("y1", 0))
            x2, y2 = float(c.get("x2", 0)), float(c.get("y2", 0))
            min_x = min(min_x, x1 - hw, x2 - hw)
            max_x = max(max_x, x1 + hw, x2 + hw)
            min_y = min(min_y, y1 - hw, y2 - hw)
            max_y = max(max_y, y1 + hw, y2 + hw)
        except (ValueError, TypeError):
            pass

    for o in obstacles:
        try:
            ox, oy = float(o.get("x", 0)), float(o.get("y", 0))
            if o.get("type") == "circle":
                rad = float(o.get("radius", 30))
                min_x = min(min_x, ox - rad)
                max_x = max(max_x, ox + rad)
                min_y = min(min_y, oy - rad)
                max_y = max(max_y, oy + rad)
            else:
                ow, oh = float(o.get("width", 0)), float(o.get("height", 0))
                min_x = min(min_x, ox)
                max_x = max(max_x, ox + ow)
                min_y = min(min_y, oy)
                max_y = max(max_y, oy + oh)
        except (ValueError, TypeError):
            pass

    fw = float(getattr(floor, "width_px", None) or getattr(floor, "width", None) or 1600.0)
    fh = float(getattr(floor, "height_px", None) or getattr(floor, "height", None) or 900.0)
    if min_x == float("inf"):
        return 0.0, 0.0, fw, fh

    return min(0.0, min_x), min(0.0, min_y), max(fw, max_x), max(fh, max_y)


def _entry_candidates(
    ctx: _GraphContext,
    x: float,
    y: float,
    floor: Floor,
    what: str,
    walls: Optional[List[Dict[str, float]]] = None,
    circle_obstacles: Optional[List[Dict[str, float]]] = None,
    rect_obstacles: Optional[List[Dict[str, float]]] = None,
) -> Tuple[List[uuid.UUID], Optional[EdgeProjection]]:
    """
    Кандидаты на вход в граф: вершины ближайшего к точке коридорного ребра
    этажа, к которому есть чистый проход без пересечения стен.
    Если точка проецируется близко (<40% длины ребра) к одной из
    вершин, возвращается только эта вершина — иначе обе.

    Если точка лежит внутри комнаты — сначала ищутся вершины в той же комнате,
    чтобы маршрут не прыгал через наружные стены.
    """
    walls_list = walls or []
    circles_list = circle_obstacles or []
    rects_list = rect_obstacles or []
    rooms_list = (floor.layout_data or {}).get("rooms", [])

    # Ограничиваем точку общими проходимыми границами этажа (не даем уйти в темную пустоту)
    min_x, min_y, max_x, max_y = _get_floor_navigable_bounds(floor)
    x = max(min_x, min(max_x, x))
    y = max(min_y, min(max_y, y))

    # Мягко смещаем точку, если она упала внутрь препятствия или стены
    x, y = _snap_to_navigable(x, y, walls_list, circles_list, rects_list, rooms_list)

    floor_nodes = [n for n in ctx.nodes.values() if n.floor_id == floor.id]
    cur_room_id = find_room_for_point(x, y, rooms_list, tolerance=8.0)

    # 1. Если точка внутри комнаты, ищем узлы графа в той же комнате с прямой видимостью
    if cur_room_id:
        room_nodes: List[Tuple[uuid.UUID, float]] = []
        for n in floor_nodes:
            n_room = find_room_for_point(n.x, n.y, rooms_list, tolerance=4.0)
            if n_room == cur_room_id:
                dist = euclidean_px(x, y, n.x, n.y)
                if is_segment_clear((x, y), (n.x, n.y), walls_list, circles_list, rects_list):
                    room_nodes.append((n.id, dist))
        if room_nodes:
            room_nodes.sort(key=lambda item: item[1])
            return [item[0] for item in room_nodes[:4]], None

    # 2. Поиск ближайших проекций на коридорные рёбра этажа
    edge_projections = find_candidate_edge_projections(
        x, y, floor.id, ctx.nodes, ctx.edges.values(), limit=12
    )

    # Если заданы стены/препятствия, фильтруем те рёбра, проход к которым режет стену
    valid_projections = []
    if walls_list or circles_list or rects_list:
        for proj in edge_projections:
            if is_segment_clear(
                (x, y), (proj.proj_x, proj.proj_y), walls_list, circles_list, rects_list
            ):
                valid_projections.append(proj)
    else:
        valid_projections = edge_projections

    if valid_projections:
        projection = valid_projections[0]
        if projection.t <= 0.4:
            return [projection.edge.from_node_id], projection
        if projection.t >= 0.6:
            return [projection.edge.to_node_id], projection
        return [projection.edge.from_node_id, projection.edge.to_node_id], projection

    # 3. Если все проекции на рёбра за стеной, ищем любые видимые вершины этажа по прямой
    visible_nodes: List[Tuple[uuid.UUID, float]] = []
    for n in floor_nodes:
        dist = euclidean_px(x, y, n.x, n.y)
        if dist <= 600.0:
            if is_segment_clear((x, y), (n.x, n.y), walls_list, circles_list, rects_list):
                visible_nodes.append((n.id, dist))

    if visible_nodes:
        visible_nodes.sort(key=lambda item: item[1])
        return [item[0] for item in visible_nodes[:6]], None

    # 4. Fallback: если были в комнате, берем ближайший узел этой комнаты
    if cur_room_id:
        room_fallback = [
            (n.id, euclidean_px(x, y, n.x, n.y))
            for n in floor_nodes
            if find_room_for_point(n.x, n.y, rooms_list, tolerance=8.0) == cur_room_id
        ]
        if room_fallback:
            room_fallback.sort(key=lambda item: item[1])
            return [room_fallback[0][0]], None

    # 5. Fallback: ближайшая проекция из всех
    if edge_projections:
        projection = edge_projections[0]
        if projection.t <= 0.4:
            return [projection.edge.from_node_id], projection
        if projection.t >= 0.6:
            return [projection.edge.to_node_id], projection
        return [projection.edge.from_node_id, projection.edge.to_node_id], projection

    nearest = find_nearest_node(x, y, floor.id, ctx.nodes)
    if nearest is not None:
        return [nearest[0].id], None
    raise RoutingError(
        f"На этаже «{floor.title}» ({what}) нет навигационного графа",
        status_code=422,
    )


def _choose_route(
    ctx: _GraphContext,
    req: RouteRequest,
    poi: POI,
    start_floor: Floor,
    target_floor: Floor,
    starts: List[uuid.UUID],
    targets: List[uuid.UUID],
    proj_a: Optional[EdgeProjection],
    proj_b: Optional[EdgeProjection],
    start_walls: Optional[List[Dict[str, float]]] = None,
    start_circles: Optional[List[Dict[str, float]]] = None,
    start_rects: Optional[List[Dict[str, float]]] = None,
    target_walls: Optional[List[Dict[str, float]]] = None,
    target_circles: Optional[List[Dict[str, float]]] = None,
    target_rects: Optional[List[Dict[str, float]]] = None,
) -> _Candidate:
    """Перебирает кандидатов A* и выбирает маршрут минимальной стоимости без коллизий со стенами."""
    best: Optional[_Candidate] = None
    target_set = set(targets)
    s_walls = start_walls or []
    s_circles = start_circles or []
    s_rects = start_rects or []
    t_walls = target_walls or []
    t_circles = target_circles or []
    t_rects = target_rects or []

    for start_id in starts:
        result = astar(
            start_id,
            target_set,
            ctx.nodes,
            ctx.adjacency,
            accessible_only=req.wheelchair_accessible_only,
        )
        if result is None:
            continue
        end_id = result.node_ids[-1]
        start_node = ctx.nodes[start_id]
        end_node = ctx.nodes[end_id]
        approach_m = euclidean_px(req.x, req.y, start_node.x, start_node.y) / start_floor.ppm
        exit_m = euclidean_px(end_node.x, end_node.y, poi.x_coord, poi.y_coord) / target_floor.ppm

        # Штраф за проход подхода или схода сквозь стены (чтобы маршрут не резал стены комнат)
        penalty_m = 0.0
        if not is_segment_clear((req.x, req.y), (start_node.x, start_node.y), s_walls, s_circles, s_rects):
            penalty_m += 1000.0
        if not is_segment_clear((end_node.x, end_node.y), (poi.x_coord, poi.y_coord), t_walls, t_circles, t_rects):
            penalty_m += 1000.0

        candidate = _Candidate(
            total_meters=approach_m + result.total_meters + exit_m + penalty_m,
            start_node_id=start_id,
            end_node_id=end_id,
            path_node_ids=result.node_ids,
            path_edge_ids=result.edge_ids,
            approach_meters=approach_m,
            exit_meters=exit_m,
        )
        if best is None or candidate.total_meters < best.total_meters:
            best = candidate

    # Вырожденный случай: А и POI проецируются на ОДНО коридорное ребро —
    # можно пройти вдоль него, ТОЛЬКО если отрезок А -> POI свободен от стен и в одной зоне!
    start_layout = getattr(start_floor, "layout_data", None) or getattr(start_floor, "layout_json", None) or {}
    s_rooms = start_layout.get("rooms", [])
    s_corridors = start_layout.get("corridors", [])
    room_a = find_room_for_point(req.x, req.y, s_rooms) if s_rooms else None
    room_b = find_room_for_point(poi.x_coord, poi.y_coord, s_rooms) if s_rooms else None
    same_room_or_open = (room_a is None or room_b is None or room_a == room_b)

    if (
        proj_a is not None
        and proj_b is not None
        and proj_a.edge.id == proj_b.edge.id
        and start_floor.id == target_floor.id
        and same_room_or_open
        and is_segment_clear((req.x, req.y), (poi.x_coord, poi.y_coord), s_walls, s_circles, s_rects)
        and is_segment_walkable((req.x, req.y), (poi.x_coord, poi.y_coord), s_rooms, s_corridors, tolerance=5.0)
    ):
        edge = proj_a.edge
        along_m = abs(proj_a.t - proj_b.t) * edge.weight_meters
        in_m = proj_a.distance_px / start_floor.ppm
        out_m = proj_b.distance_px / target_floor.ppm
        direct = _Candidate(
            total_meters=in_m + along_m + out_m,
            start_node_id=None,
            end_node_id=None,
            path_node_ids=[],
            path_edge_ids=[edge.id],
            approach_meters=in_m,
            exit_meters=out_m,
        )
        if best is None or direct.total_meters < best.total_meters:
            best = direct

    if best is None:
        # Fallback: пробуем все видимые узлы этажа старта и этажа цели
        start_floor_nodes = [n for n in ctx.nodes.values() if n.floor_id == start_floor.id]
        target_floor_nodes = [n for n in ctx.nodes.values() if n.floor_id == target_floor.id]
        all_vis_starts = [
            n.id for n in start_floor_nodes
            if is_segment_clear((req.x, req.y), (n.x, n.y), s_walls, s_circles, s_rects)
        ]
        all_vis_targets = [
            n.id for n in target_floor_nodes
            if is_segment_clear((n.x, n.y), (poi.x_coord, poi.y_coord), t_walls, t_circles, t_rects)
        ]
        if all_vis_starts and all_vis_targets:
            fb_target_set = set(all_vis_targets)
            for sid in all_vis_starts:
                res = astar(
                    sid,
                    fb_target_set,
                    ctx.nodes,
                    ctx.adjacency,
                    accessible_only=req.wheelchair_accessible_only,
                )
                if res is not None:
                    eid = res.node_ids[-1]
                    s_node = ctx.nodes[sid]
                    e_node = ctx.nodes[eid]
                    app_m = euclidean_px(req.x, req.y, s_node.x, s_node.y) / start_floor.ppm
                    ex_m = euclidean_px(e_node.x, e_node.y, poi.x_coord, poi.y_coord) / target_floor.ppm
                    cand = _Candidate(
                        total_meters=app_m + res.total_meters + ex_m,
                        start_node_id=sid,
                        end_node_id=eid,
                        path_node_ids=res.node_ids,
                        path_edge_ids=res.edge_ids,
                        approach_meters=app_m,
                        exit_meters=ex_m,
                    )
                    if best is None or cand.total_meters < best.total_meters:
                        best = cand

    if best is None and start_floor.id == target_floor.id:
        # Прямой проход, если между точками нет ни одной стены и препятствия
        if is_segment_clear((req.x, req.y), (poi.x_coord, poi.y_coord), s_walls, s_circles, s_rects):
            dist_m = euclidean_px(req.x, req.y, poi.x_coord, poi.y_coord) / start_floor.ppm
            best = _Candidate(
                total_meters=dist_m,
                start_node_id=None,
                end_node_id=None,
                path_node_ids=[],
                path_edge_ids=[],
                approach_meters=dist_m,
                exit_meters=0.0,
            )

    if best is None:
        detail = (
            "Доступный маршрут без лестниц не найден"
            if req.wheelchair_accessible_only
            else "Маршрут не найден: части графа не связаны между собой"
        )
        raise RoutingError(detail, status_code=404)
    return best


def _build_legs(
    ctx: _GraphContext, candidate: _Candidate
) -> Tuple[List[instr.RouteLeg], List[RoutePathNodeRead], List[RoutePathEdgeRead]]:
    """Собирает «ноги» маршрута и читаемые представления вершин/рёбер пути."""
    legs: List[instr.RouteLeg] = []
    path_nodes: List[RoutePathNodeRead] = []
    path_edges: List[RoutePathEdgeRead] = []

    for node_id in candidate.path_node_ids:
        node = ctx.nodes[node_id]
        path_nodes.append(
            RoutePathNodeRead(
                id=node.id,
                floor_id=node.floor_id,
                floor_number=node.floor_number,
                x=node.x,
                y=node.y,
                node_type=NavNodeType(node.node_type),
            )
        )

    for i, edge_id in enumerate(candidate.path_edge_ids):
        edge = ctx.edges[edge_id]
        if candidate.path_node_ids:
            # Направление прохождения ребра: от текущей вершины пути к следующей
            from_id = candidate.path_node_ids[i]
            to_id = candidate.path_node_ids[i + 1]
            a, b = ctx.nodes[from_id], ctx.nodes[to_id]
            legs.append(
                instr.RouteLeg(
                    edge_id=edge.id,
                    kind=edge.kind,
                    from_node_id=from_id,
                    to_node_id=to_id,
                    from_x=a.x,
                    from_y=a.y,
                    to_x=b.x,
                    to_y=b.y,
                    weight_meters=edge.weight_meters,
                    from_floor_id=a.floor_id,
                    to_floor_id=b.floor_id,
                    from_floor_number=a.floor_number,
                    to_floor_number=b.floor_number,
                )
            )
        else:
            # Прямой проход вдоль одного ребра без захода в вершины:
            # «нога» не создаётся — инструкция строится по точкам А и POI.
            from_id, to_id = edge.from_node_id, edge.to_node_id
        path_edges.append(
            RoutePathEdgeRead(
                id=edge.id,
                kind=NavEdgeKind(edge.kind),
                from_node_id=from_id,
                to_node_id=to_id,
                weight_meters=edge.weight_meters,
            )
        )
    return legs, path_nodes, path_edges


def _adjacency_bearings(ctx: _GraphContext) -> Dict[uuid.UUID, List[Tuple[uuid.UUID, float]]]:
    """
    Азимуты коридорных рёбер от каждой вершины — для анализа развилок.
    Межэтажные рёбра не учитываем: на плане этажа они не выглядят проходом.
    """
    bearings: Dict[uuid.UUID, List[Tuple[uuid.UUID, float]]] = {}
    for edge in ctx.edges.values():
        if edge.kind != NavEdgeKind.CORRIDOR.value:
            continue
        a = ctx.nodes.get(edge.from_node_id)
        b = ctx.nodes.get(edge.to_node_id)
        if a is None or b is None:
            continue
        bearings.setdefault(a.id, []).append(
            (edge.id, bearing_deg(a.x, a.y, b.x, b.y))
        )
        bearings.setdefault(b.id, []).append(
            (edge.id, bearing_deg(b.x, b.y, a.x, a.y))
        )
    return bearings


async def build_route(
    db: AsyncSession,
    space: Space,
    req: RouteRequest,
) -> RouteResponse:
    """Строит маршрут от точки А до POI. Ошибки — RoutingError."""
    # --- Валидация входа ---
    poi = await poi_repo.get_by_id(db, req.to_poi_id)
    if poi is None:
        raise RoutingError("POI not found", status_code=404)

    floors, nodes_db, edges_db = await navigation_repo.get_space_graph(db, space.id)
    ctx = _build_context(floors, nodes_db, edges_db)

    start_floor = _floor_or_error(ctx, req.floor_id, "Стартовый этаж")
    if not ctx.nodes:
        from app.services.auto_graph import generate_auto_graph
        for fl in floors:
            floor_pois = await poi_repo.list_by_floor(db, fl.id)
            nodes_payload, edges_payload = generate_auto_graph(
                width=fl.width_px or 2000,
                height=fl.height_px or 1500,
                layout=fl.layout_data or {},
                pois=floor_pois,
            )
            if nodes_payload:
                if not fl.ppm or fl.ppm <= 0:
                    fl.ppm = 25.0
                await navigation_repo.replace_floor_graph(
                    db, fl, nodes_payload, edges_payload
                )
        await db.flush()
        floors, nodes_db, edges_db = await navigation_repo.get_space_graph(db, space.id)
        ctx = _build_context(floors, nodes_db, edges_db)

    if not ctx.nodes:
        raise RoutingError("В пространстве пока нет точек или элементов планировки для маршрута", status_code=422)

    target_floor = _floor_or_error(ctx, poi.floor_id, "Этаж целевой POI")

    start_layout = start_floor.layout_data or {}
    target_layout = target_floor.layout_data or {}

    start_walls = start_layout.get("walls", [])
    start_circles = [
        {"x": float(o["x"]), "y": float(o["y"]), "radius": float(o.get("radius", 30))}
        for o in start_layout.get("obstacles", [])
        if o.get("type") == "circle"
    ]
    start_rects = [
        {
            "x": float(o["x"]),
            "y": float(o["y"]),
            "width": float(o.get("width", 50)),
            "height": float(o.get("height", 50)),
        }
        for o in start_layout.get("obstacles", [])
        if o.get("type") == "rect"
    ]

    target_walls = target_layout.get("walls", [])
    target_circles = [
        {"x": float(o["x"]), "y": float(o["y"]), "radius": float(o.get("radius", 30))}
        for o in target_layout.get("obstacles", [])
        if o.get("type") == "circle"
    ]
    target_rects = [
        {
            "x": float(o["x"]),
            "y": float(o["y"]),
            "width": float(o.get("width", 50)),
            "height": float(o.get("height", 50)),
        }
        for o in target_layout.get("obstacles", [])
        if o.get("type") == "rect"
    ]

    # --- Кандидаты на вход/выход с учётом стен и препятствий ---
    starts, proj_a = _entry_candidates(
        ctx, req.x, req.y, start_floor, "точка А",
        walls=start_walls, circle_obstacles=start_circles, rect_obstacles=start_rects
    )
    targets, proj_b = _entry_candidates(
        ctx, poi.x_coord, poi.y_coord, target_floor, "POI",
        walls=target_walls, circle_obstacles=target_circles, rect_obstacles=target_rects
    )

    # --- Выбор лучшего маршрута ---
    best = _choose_route(
        ctx, req, poi, start_floor, target_floor, starts, targets, proj_a, proj_b,
        start_walls=start_walls, start_circles=start_circles, start_rects=start_rects,
        target_walls=target_walls, target_circles=target_circles, target_rects=target_rects,
    )

    # --- Сборка ответа ---
    legs, path_nodes, path_edges = _build_legs(ctx, best)

    landmarks = await _load_landmarks(db, ctx, poi)
    steps_drafts = instr.build_steps(
        start_x=req.x,
        start_y=req.y,
        start_floor_id=start_floor.id,
        legs=legs,
        target_poi_title=poi.title,
        target_poi_x=poi.x_coord,
        target_poi_y=poi.y_coord,
        target_poi_id=poi.id,
        adjacency_bearings=_adjacency_bearings(ctx),
        landmarks=landmarks,
        ppm_by_floor={f.id: f.ppm for f in ctx.floors.values()},
    )
    steps = [
        RouteStepRead(
            kind=s.kind,
            text=s.text,
            distance_meters=(
                round(s.distance_meters, 1) if s.distance_meters is not None else None
            ),
            floor_id=s.floor_id,
            node_ids=s.node_ids,
        )
        for s in steps_drafts
    ]

    panorama_ids: List[uuid.UUID] = []
    for node_id in best.path_node_ids:
        pano_id = ctx.nodes[node_id].panorama_id
        if pano_id is not None and pano_id not in panorama_ids:
            panorama_ids.append(pano_id)

    entry = RouteEndpointInfo(
        point=RoutePointRead(x=req.x, y=req.y, floor_id=start_floor.id),
        projected_point=(
            RoutePointRead(x=proj_a.proj_x, y=proj_a.proj_y, floor_id=start_floor.id)
            if proj_a
            else None
        ),
        node_id=best.start_node_id,
        walk_distance_meters=round(best.approach_meters, 1),
    )
    exit_info = RouteEndpointInfo(
        point=RoutePointRead(x=poi.x_coord, y=poi.y_coord, floor_id=target_floor.id),
        projected_point=(
            RoutePointRead(x=proj_b.proj_x, y=proj_b.proj_y, floor_id=target_floor.id)
            if proj_b
            else None
        ),
        node_id=best.end_node_id,
        walk_distance_meters=round(best.exit_meters, 1),
    )

    total = round(best.total_meters, 1)
    return RouteResponse(
        total_distance_meters=total,
        estimated_time_seconds=max(1, round(total / WALKING_SPEED_MPS)),
        entry=entry,
        exit=exit_info,
        nodes=path_nodes,
        edges=path_edges,
        steps=steps,
        panorama_ids=panorama_ids,
    )


async def _load_landmarks(
    db: AsyncSession, ctx: _GraphContext, target_poi: POI
) -> List[instr.Landmark]:
    """POI-ориентиры на этажах маршрута (целевая POI исключается)."""
    floor_ids = {n.floor_id for n in ctx.nodes.values()}
    landmarks: List[instr.Landmark] = []
    for floor_id in floor_ids:
        for poi in await poi_repo.list_by_floor(db, floor_id):
            if poi.id == target_poi.id:
                continue
            landmarks.append(
                instr.Landmark(
                    id=poi.id,
                    title=poi.title,
                    x=poi.x_coord,
                    y=poi.y_coord,
                    floor_id=poi.floor_id,
                )
            )
    return landmarks
