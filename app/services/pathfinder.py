"""
Чистая математика навигации: геометрия на 2D-плане и алгоритм A*.

Модуль не зависит от БД и FastAPI — все функции работают с простыми
датаклассами, что позволяет покрывать их быстрыми юнит-тестами.

ВАЖНО про систему координат: координаты (x, y) — пиксели чертежа этажа,
ось Y направлена ВНИЗ (как в изображениях). Поэтому положительный знак
векторного произведения / положительный поворот азимута соответствует
повороту НАПРАВО с точки зрения идущего человека (см. turn_direction).
"""

from __future__ import annotations

import heapq
import math
import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Константы стоимости и скорости
# ---------------------------------------------------------------------------

#: Вес ребра-лестницы — эквивалент 35 метров пути по прямой (по ТЗ).
STAIRS_WEIGHT_METERS: float = 35.0
#: Вес ребра-лифта — эквивалент ожидания кабины + поездки (~30 м пути).
ELEVATOR_WEIGHT_METERS: float = 30.0
#: Средняя пешеходная скорость для оценки времени маршрута, м/с.
WALKING_SPEED_MPS: float = 1.2


# ---------------------------------------------------------------------------
# Структуры графа (чистые, без ORM)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphNode:
    """Вершина графа для расчётов."""

    id: uuid.UUID
    floor_id: uuid.UUID
    x: float  # px
    y: float  # px
    ppm: float  # масштаб этажа (pixels per meter) — нужен эвристике A*
    floor_number: int = 0
    node_type: str = "walkway"
    panorama_id: Optional[uuid.UUID] = None


@dataclass(frozen=True)
class GraphEdge:
    """Ребро графа для расчётов. Вес уже в метрах (вычислен на сервере)."""

    id: uuid.UUID
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    kind: str  # "corridor" | "stairs" | "elevator"
    weight_meters: float
    is_accessible: bool = True
    bidirectional: bool = True


@dataclass
class EdgeProjection:
    """Результат проекции точки на ребро графа."""

    edge: GraphEdge
    proj_x: float  # координаты проекции на отрезке (px)
    proj_y: float
    t: float  # параметр положения проекции на отрезке [0..1]
    distance_px: float  # расстояние от точки до отрезка (px)


@dataclass
class PathResult:
    """
    Результат работы A*: цепочка вершин, пройденные рёбра (в том же
    порядке, len = len(node_ids) - 1) и стоимость пути в метрах.
    """

    node_ids: List[uuid.UUID]
    edge_ids: List[uuid.UUID]
    total_meters: float


# ---------------------------------------------------------------------------
# Базовая геометрия
# ---------------------------------------------------------------------------


def euclidean_px(x1: float, y1: float, x2: float, y2: float) -> float:
    """Евклидово расстояние между двумя точками плана в пикселях."""
    return math.hypot(x2 - x1, y2 - y1)


def corridor_weight_meters(
    x1: float, y1: float, x2: float, y2: float, ppm: float
) -> float:
    """
    Вес коридорного ребра в метрах: евклидово расстояние между вершинами
    в пикселях, делённое на масштаб этажа (pixels per meter).
    """
    if ppm <= 0:
        raise ValueError("ppm (pixels per meter) must be positive")
    return euclidean_px(x1, y1, x2, y2) / ppm


def project_point_on_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> Tuple[float, float, float, float]:
    """
    Проекция точки P на отрезок AB.

    Возвращает (proj_x, proj_y, t, distance_px):
      - proj_x/proj_y — ближайшая к P точка отрезка;
      - t — её параметр на отрезке: 0.0 = A, 1.0 = B (зажат в [0, 1]);
      - distance_px — расстояние от P до отрезка в пикселях.
    """
    abx, aby = bx - ax, by - ay
    length_sq = abx * abx + aby * aby
    if length_sq == 0.0:
        # Вырожденный отрезок (A == B) — проекция совпадает с A.
        return ax, ay, 0.0, euclidean_px(px, py, ax, ay)
    t = ((px - ax) * abx + (py - ay) * aby) / length_sq
    t = max(0.0, min(1.0, t))
    proj_x, proj_y = ax + t * abx, ay + t * aby
    return proj_x, proj_y, t, euclidean_px(px, py, proj_x, proj_y)


def bearing_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Азимут направления (x1,y1) -> (x2,y2) в градусах, диапазон (-180..180].

    0° — восток (вправо по плану), 90° — юг (вниз по плану, т.к. ось Y
    направлена вниз), ±180° — запад, -90° — север (вверх по плану).
    """
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def signed_turn_deg(bearing_from: float, bearing_to: float) -> float:
    """
    Знаковый угол поворота с направления bearing_from на bearing_to,
    диапазон (-180..180]. Положительный знак = поворот НАПРАВО для идущего
    (из-за направленной вниз оси Y в пиксельных координатах).
    """
    return (bearing_to - bearing_from + 180.0) % 360.0 - 180.0


def turn_side(x1: float, y1: float, x2: float, y2: float, px: float, py: float) -> str:
    """
    Сторона точки P относительно направления движения (x1,y1) -> (x2,y2).

    Возвращает "right" или "left" с точки зрения идущего человека
    (учитывает направленную вниз ось Y: cross > 0 => точка справа).
    """
    cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    return "right" if cross > 0 else "left"


# ---------------------------------------------------------------------------
# Работа с графом
# ---------------------------------------------------------------------------


def build_adjacency(
    nodes: Dict[uuid.UUID, GraphNode],
    edges: Iterable[GraphEdge],
) -> Dict[uuid.UUID, List[Tuple[uuid.UUID, GraphEdge]]]:
    """
    Строит списки смежности node_id -> [(neighbor_id, edge), ...].
    Двунаправленные рёбра добавляются в обе стороны.
    """
    adjacency: Dict[uuid.UUID, List[Tuple[uuid.UUID, GraphEdge]]] = {
        node_id: [] for node_id in nodes
    }
    for edge in edges:
        if edge.from_node_id not in nodes or edge.to_node_id not in nodes:
            continue
        adjacency[edge.from_node_id].append((edge.to_node_id, edge))
        if edge.bidirectional:
            adjacency[edge.to_node_id].append((edge.from_node_id, edge))
    return adjacency


def find_nearest_edge_projection(
    x: float,
    y: float,
    floor_id: uuid.UUID,
    nodes: Dict[uuid.UUID, GraphNode],
    edges: Iterable[GraphEdge],
    allowed_kinds: Set[str] = frozenset({"corridor"}),
) -> Optional[EdgeProjection]:
    """
    Ищет ребро заданного этажа, ближайшее к точке (x, y), через расстояние
    от точки до отрезка ребра. Рассматриваются только рёбра указанных типов,
    обе вершины которых лежат на заданном этаже.
    """
    candidates = find_candidate_edge_projections(
        x, y, floor_id, nodes, edges, allowed_kinds, limit=1
    )
    return candidates[0] if candidates else None


def find_candidate_edge_projections(
    x: float,
    y: float,
    floor_id: uuid.UUID,
    nodes: Dict[uuid.UUID, GraphNode],
    edges: Iterable[GraphEdge],
    allowed_kinds: Set[str] = frozenset({"corridor"}),
    limit: int = 5,
) -> List[EdgeProjection]:
    """
    Возвращает список ближайших к точке (x, y) рёбер этажа, отсортированных
    по евклидову расстоянию до отрезка.
    """
    projections: List[EdgeProjection] = []
    for edge in edges:
        if edge.kind not in allowed_kinds:
            continue
        a = nodes.get(edge.from_node_id)
        b = nodes.get(edge.to_node_id)
        if a is None or b is None:
            continue
        if a.floor_id != floor_id or b.floor_id != floor_id:
            continue
        proj_x, proj_y, t, dist = project_point_on_segment(x, y, a.x, a.y, b.x, b.y)
        projections.append(
            EdgeProjection(edge=edge, proj_x=proj_x, proj_y=proj_y, t=t, distance_px=dist)
        )
    projections.sort(key=lambda p: p.distance_px)
    return projections[:limit]


def find_nearest_node(
    x: float,
    y: float,
    floor_id: uuid.UUID,
    nodes: Dict[uuid.UUID, GraphNode],
) -> Optional[Tuple[GraphNode, float]]:
    """
    Ближайшая к точке вершина этажа. Fallback на случай, когда на этаже
    есть вершины, но нет рёбер (проецировать не на что).
    """
    best: Optional[Tuple[GraphNode, float]] = None
    for node in nodes.values():
        if node.floor_id != floor_id:
            continue
        dist = euclidean_px(x, y, node.x, node.y)
        if best is None or dist < best[1]:
            best = (node, dist)
    return best


# ---------------------------------------------------------------------------
# Алгоритм A*
# ---------------------------------------------------------------------------


def _heuristic_meters(node: GraphNode, targets: Sequence[GraphNode]) -> float:
    """
    Эвристика A* в метрах: минимум евклидова расстояния до целей,
    переведённого через ppm этажа текущей вершины.

    Межэтажные рёбра имеют вес не меньше эквивалентного «прямого» веса
    (лестница = 35 м при почти нулевом смещении по плану), поэтому
    эвристика не переоценивает реальную стоимость и A* остаётся корректным.
    """
    return min(
        euclidean_px(node.x, node.y, t.x, t.y) / node.ppm for t in targets
    )


def astar(
    start_id: uuid.UUID,
    target_ids: Set[uuid.UUID],
    nodes: Dict[uuid.UUID, GraphNode],
    adjacency: Dict[uuid.UUID, List[Tuple[uuid.UUID, GraphEdge]]],
    accessible_only: bool = False,
) -> Optional[PathResult]:
    """
    Классический A* от start_id до ближайшей из вершин target_ids.

    - Веса рёбер берутся из БД (метры).
    - При accessible_only=True рёбра с is_accessible=False (лестницы)
      исключаются из рассмотрения.
    - Возвращает None, если ни одна цель недостижима.
    """
    if start_id not in nodes or not target_ids:
        return None
    targets = [nodes[t] for t in target_ids if t in nodes]
    if not targets:
        return None
    if start_id in target_ids:
        return PathResult(node_ids=[start_id], edge_ids=[], total_meters=0.0)

    start = nodes[start_id]
    # heap: (f_score, counter, node_id)
    counter = 0
    open_heap: List[Tuple[float, int, uuid.UUID]] = [
        (_heuristic_meters(start, targets), counter, start_id)
    ]
    g_score: Dict[uuid.UUID, float] = {start_id: 0.0}
    came_from: Dict[uuid.UUID, Tuple[uuid.UUID, GraphEdge]] = {}
    closed: Set[uuid.UUID] = set()

    while open_heap:
        _, _, current_id = heapq.heappop(open_heap)
        if current_id in closed:
            continue
        if current_id in target_ids:
            # Восстанавливаем путь и пройденные рёбра
            path = [current_id]
            edge_path: List[uuid.UUID] = []
            while path[-1] in came_from:
                prev_id, via_edge = came_from[path[-1]]
                edge_path.append(via_edge.id)
                path.append(prev_id)
            path.reverse()
            edge_path.reverse()
            return PathResult(
                node_ids=path, edge_ids=edge_path, total_meters=g_score[current_id]
            )
        closed.add(current_id)
        current = nodes[current_id]

        for neighbor_id, edge in adjacency.get(current_id, []):
            if accessible_only and not edge.is_accessible:
                continue
            if neighbor_id in closed:
                continue
            tentative_g = g_score[current_id] + edge.weight_meters
            if tentative_g < g_score.get(neighbor_id, math.inf):
                g_score[neighbor_id] = tentative_g
                came_from[neighbor_id] = (current_id, edge)
                neighbor = nodes[neighbor_id]
                counter += 1
                f = tentative_g + _heuristic_meters(neighbor, targets)
                heapq.heappush(open_heap, (f, counter, neighbor_id))

    return None
