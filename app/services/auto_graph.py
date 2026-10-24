"""
Автоматическая генерация навигационного графа на бэкенде.

Строит проходимый граф путей по 2D-планировке помещения (комнаты, коридоры,
стены, круглые и прямоугольные объекты/препятствия) и точкам интереса (POI).

Учитывает:
- Точки прикрепления для POI (входы, лавочки, урны, торговые точки, стенды).
- Огибание углов стен и прямоугольных препятствий с безопасным отступом.
- Огибание круглых объектов (колонны, круглые стенды/островки) по касательным точкам обхода.
- Повороты коридоров и пересечения проходов.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.navigation import NavNodeType


def line_intersection(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    p4: Tuple[float, float],
) -> bool:
    """Проверяет пересечение двух отрезков p1-p2 и p3-p4."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
    if abs(denom) < 1e-9:
        return False  # Параллельны

    ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denom
    ub = ((x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)) / denom

    # Строгое пересечение внутри отрезков
    return 0.01 <= ua <= 0.99 and 0.01 <= ub <= 0.99


def distance_point_to_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    """Расстояние от точки P до отрезка AB."""
    abx, aby = bx - ax, by - ay
    l2 = abx * abx + aby * aby
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / l2))
    proj_x = ax + t * abx
    proj_y = ay + t * aby
    return math.hypot(px - proj_x, py - proj_y)


def is_segment_clear(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    walls: List[Dict[str, float]],
    circle_obstacles: List[Dict[str, float]],
    rect_obstacles: List[Dict[str, float]],
) -> bool:
    """Проверяет, свободен ли отрезок p1-p2 от стен и препятствий."""
    # 1. Проверка пересечения со стенами
    for w in walls:
        w_p1 = (w["x1"], w["y1"])
        w_p2 = (w["x2"], w["y2"])
        if line_intersection(p1, p2, w_p1, w_p2):
            return False

    # 2. Проверка столкновения с круглыми объектами (колонны/фонтаны/столы)
    for c in circle_obstacles:
        cx, cy, r = c["x"], c["y"], c["radius"]
        if distance_point_to_segment(cx, cy, p1[0], p1[1], p2[0], p2[1]) < r:
            return False

    # 3. Проверка пересечения с прямоугольными объектами
    for r in rect_obstacles:
        rx, ry, rw, rh = r["x"], r["y"], r["width"], r["height"]
        corners = [
            ((rx, ry), (rx + rw, ry)),
            ((rx + rw, ry), (rx + rw, ry + rh)),
            ((rx + rw, ry + rh), (rx, ry + rh)),
            ((rx, ry + rh), (rx, ry)),
        ]
        for edge_p1, edge_p2 in corners:
            if line_intersection(p1, p2, edge_p1, edge_p2):
                return False

    return True


def generate_auto_graph(
    width: int,
    height: int,
    layout: Dict[str, Any],
    pois: List[Any],
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int]]]:
    """
    Генерирует навигационный граф по 2D-планировке и точкам POI.

    Возвращает:
      - nodes_payload: список словарей узлов {'x', 'y', 'node_type', 'ref'}
      - edges_payload: список кортежей (from_index, to_index)
    """
    rooms: List[Dict[str, Any]] = layout.get("rooms", [])
    walls: List[Dict[str, Any]] = layout.get("walls", [])
    corridors: List[Dict[str, Any]] = layout.get("corridors", [])
    obstacles: List[Dict[str, Any]] = layout.get("obstacles", [])

    circle_obstacles: List[Dict[str, float]] = [
        {"x": float(o["x"]), "y": float(o["y"]), "radius": float(o.get("radius", 30))}
        for o in obstacles
        if o.get("type") == "circle"
    ]
    rect_obstacles: List[Dict[str, float]] = [
        {
            "x": float(o["x"]),
            "y": float(o["y"]),
            "width": float(o.get("width", 50)),
            "height": float(o.get("height", 50)),
        }
        for o in obstacles
        if o.get("type") == "rect"
    ]

    nodes: List[Dict[str, Any]] = []
    edges_set: Set[Tuple[int, int]] = set()

    def add_node(x: float, y: float, node_type: str = "walkway") -> int:
        # Ограничиваем координаты границами плана
        cx = max(10.0, min(float(width) - 10.0, round(x, 1)))
        cy = max(10.0, min(float(height) - 10.0, round(y, 1)))
        # Проверяем, нет ли уже узла в этой же точке (радиус 15px)
        for idx, n in enumerate(nodes):
            if math.hypot(n["x"] - cx, n["y"] - cy) < 15.0:
                return idx
        idx = len(nodes)
        nodes.append({
            "x": cx,
            "y": cy,
            "node_type": node_type,
            "ref": f"auto_{idx}",
        })
        return idx

    def add_edge(idx1: int, idx2: int) -> None:
        if idx1 == idx2:
            return
        p1 = (nodes[idx1]["x"], nodes[idx1]["y"])
        p2 = (nodes[idx2]["x"], nodes[idx2]["y"])
        if is_segment_clear(p1, p2, walls, circle_obstacles, rect_obstacles):
            pair = (min(idx1, idx2), max(idx1, idx2))
            edges_set.add(pair)

    # 1. Добавляем точки прикрепления для всех POI
    poi_node_indices: List[int] = []
    for poi in pois:
        px = getattr(poi, "x_coord", None) or getattr(poi, "x", 0.0)
        py = getattr(poi, "y_coord", None) or getattr(poi, "y", 0.0)
        category = getattr(poi, "category", "")
        if isinstance(category, str):
            category_val = category
        else:
            category_val = getattr(category, "value", "")

        node_type = "door" if category_val in ("entrance", "exit") else "walkway"
        poi_idx = add_node(px, py, node_type=node_type)
        poi_node_indices.append(poi_idx)

    # 2. Добавляем узлы и огибание для круглых объектов (колонны, круглые стенды)
    circle_ring_indices: List[List[int]] = []
    for c in circle_obstacles:
        cx, cy, r = c["x"], c["y"], c["radius"]
        clearance = r + 30.0  # Отступ безопасности от объекта
        ring_indices: List[int] = []
        # 8 точек обхода по кругу
        for k in range(8):
            angle = k * (2 * math.pi / 8)
            bx = cx + clearance * math.cos(angle)
            by = cy + clearance * math.sin(angle)
            n_idx = add_node(bx, by, node_type="walkway")
            ring_indices.append(n_idx)

        # Соединяем соседние точки кольца обхода
        for k in range(8):
            add_edge(ring_indices[k], ring_indices[(k + 1) % 8])
        circle_ring_indices.append(ring_indices)

    # 3. Добавляем узлы огибания для прямоугольных препятствий
    rect_corner_indices: List[List[int]] = []
    for r in rect_obstacles:
        rx, ry, rw, rh = r["x"], r["y"], r["width"], r["height"]
        margin = 30.0
        corners = [
            (rx - margin, ry - margin),
            (rx + rw + margin, ry - margin),
            (rx + rw + margin, ry + rh + margin),
            (rx - margin, ry + rh + margin),
        ]
        c_indices = [add_node(x, y, node_type="walkway") for x, y in corners]
        for k in range(4):
            add_edge(c_indices[k], c_indices[(k + 1) % 4])
        rect_corner_indices.append(c_indices)

    # 3.1. Добавляем узлы обхода углов и поворотов стен
    for w in walls:
        x1, y1 = float(w["x1"]), float(w["y1"])
        x2, y2 = float(w["x2"]), float(w["y2"])
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length > 1e-3:
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux  # нормаль
            margin = 35.0
            wall_bypasses = [
                (x1 - margin * ux, y1 - margin * uy),
                (x1 - margin * ux + margin * nx, y1 - margin * uy + margin * ny),
                (x1 - margin * ux - margin * nx, y1 - margin * uy - margin * ny),
                (x1 + margin * nx, y1 + margin * ny),
                (x1 - margin * nx, y1 - margin * ny),
                (x2 + margin * ux, y2 + margin * uy),
                (x2 + margin * ux + margin * nx, y2 + margin * uy + margin * ny),
                (x2 + margin * ux - margin * nx, y2 + margin * uy - margin * ny),
                (x2 + margin * nx, y2 + margin * ny),
                (x2 - margin * nx, y2 - margin * ny),
            ]
            for bx, by in wall_bypasses:
                if 10.0 <= bx <= width - 10.0 and 10.0 <= by <= height - 10.0:
                    clear_point = True
                    for c in circle_obstacles:
                        if math.hypot(bx - c["x"], by - c["y"]) <= c["radius"] + 10.0:
                            clear_point = False
                            break
                    if clear_point:
                        for r in rect_obstacles:
                            if (
                                r["x"] - 5.0 <= bx <= r["x"] + r["width"] + 5.0
                                and r["y"] - 5.0 <= by <= r["y"] + r["height"] + 5.0
                            ):
                                clear_point = False
                                break
                    if clear_point:
                        add_node(bx, by, node_type="walkway")

    # 4. Добавляем узлы для комнат и центров зон
    room_center_indices: List[int] = []
    for room in rooms:
        rx = float(room.get("x", 0))
        ry = float(room.get("y", 0))
        rw = float(room.get("width", 200))
        rh = float(room.get("height", 150))
        rc_idx = add_node(rx + rw / 2, ry + rh / 2, node_type="walkway")
        room_center_indices.append(rc_idx)

    # 5. Добавляем коридоры / проходы (если они начерчены в редакторе)
    corridor_node_indices: List[int] = []
    for corr in corridors:
        x1, y1 = float(corr["x1"]), float(corr["y1"])
        x2, y2 = float(corr["x2"]), float(corr["y2"])
        length = math.hypot(x2 - x1, y2 - y1)
        # Разбиваем длинный коридор на шаги по ~100px для плавного построения маршрута
        steps = max(1, int(length // 100))
        prev_idx = add_node(x1, y1, node_type="walkway")
        corridor_node_indices.append(prev_idx)
        for s in range(1, steps + 1):
            t = s / steps
            curr_idx = add_node(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, node_type="walkway")
            corridor_node_indices.append(curr_idx)
            add_edge(prev_idx, curr_idx)
            prev_idx = curr_idx

    # 6. Если коридоров мало или нет, генерируем сетку видимости (visibility graph)
    # Соединяем POI и центры комнат с ближайшими узлами обхода препятствий и между собой
    all_key_nodes = list(range(len(nodes)))
    for i in all_key_nodes:
        p1 = (nodes[i]["x"], nodes[i]["y"])
        # Сортируем остальных кандидатов по расстоянию
        candidates: List[Tuple[float, int]] = []
        for j in all_key_nodes:
            if i == j:
                continue
            p2 = (nodes[j]["x"], nodes[j]["y"])
            dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            # Ограничиваем максимальное расстояние связности (до 450px)
            if dist <= 450.0:
                candidates.append((dist, j))

        candidates.sort(key=lambda item: item[0])
        # Соединяем с 5-8 ближайшими видимыми узлами
        connected_count = 0
        for dist, j in candidates:
            if connected_count >= 6:
                break
            p2 = (nodes[j]["x"], nodes[j]["y"])
            if is_segment_clear(p1, p2, walls, circle_obstacles, rect_obstacles):
                add_edge(i, j)
                connected_count += 1

    # Гарантируем, что каждая POI соединена хотя бы с 1 ближайшим видимым узлом
    for poi_idx in poi_node_indices:
        p_poi = (nodes[poi_idx]["x"], nodes[poi_idx]["y"])
        has_edge = any(poi_idx in e for e in edges_set)
        if not has_edge:
            closest_dist = float("inf")
            best_other = None
            for other_idx in range(len(nodes)):
                if other_idx == poi_idx:
                    continue
                p_other = (nodes[other_idx]["x"], nodes[other_idx]["y"])
                dist = math.hypot(p_other[0] - p_poi[0], p_other[1] - p_poi[1])
                if dist < closest_dist and is_segment_clear(p_poi, p_other, walls, circle_obstacles, rect_obstacles):
                    closest_dist = dist
                    best_other = other_idx
            if best_other is not None:
                add_edge(poi_idx, best_other)

    edges_payload = list(edges_set)
    return nodes, edges_payload
