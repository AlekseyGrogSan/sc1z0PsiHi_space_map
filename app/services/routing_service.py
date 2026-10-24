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


def _entry_candidates(
    ctx: _GraphContext,
    x: float,
    y: float,
    floor: Floor,
    what: str,
) -> Tuple[List[uuid.UUID], Optional[EdgeProjection]]:
    """
    Кандидаты на вход в граф: вершины ближайшего к точке коридорного ребра
    этажа. Если точка проецируется близко (<40% длины ребра) к одной из
    вершин, возвращается только эта вершина — иначе обе.

    Fallback — ближайшая вершина этажа (если рёбер нет вовсе).
    """
    projection = find_nearest_edge_projection(
        x, y, floor.id, ctx.nodes, ctx.edges.values()
    )
    if projection is not None:
        # Если точка практически лежит у одной из вершин ребра — достаточно
        # только этой вершины, иначе обе. Порог 0.4/0.6 выбран
        # эвристически: POI возле стенда реально находится прямо у вершины
        # графа, а не на полпути по коридору (второй конец ребра был бы
        # ложным кандидатом, дающим пешеходу команду «пройти 6 м через
        # открытое пространство»).
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
) -> _Candidate:
    """Перебирает кандидатов A* и выбирает маршрут минимальной стоимости."""
    best: Optional[_Candidate] = None
    target_set = set(targets)

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
        candidate = _Candidate(
            total_meters=approach_m + result.total_meters + exit_m,
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
    # можно пройти вдоль него, не заходя в вершины.
    if (
        proj_a is not None
        and proj_b is not None
        and proj_a.edge.id == proj_b.edge.id
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
    target_floor = _floor_or_error(ctx, poi.floor_id, "Этаж целевой POI")
    if not ctx.nodes:
        raise RoutingError("В пространстве пока нет навигационного графа", status_code=422)

    # --- Кандидаты на вход/выход ---
    starts, proj_a = _entry_candidates(ctx, req.x, req.y, start_floor, "точка А")
    targets, proj_b = _entry_candidates(ctx, poi.x_coord, poi.y_coord, target_floor, "POI")

    # --- Выбор лучшего маршрута ---
    best = _choose_route(
        ctx, req, poi, start_floor, target_floor, starts, targets, proj_a, proj_b
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
