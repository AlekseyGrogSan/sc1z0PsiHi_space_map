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

    # Отрезок луча внутри (0.001..0.999), а отрезок стены p3-p4 полностью [-0.01..1.01] (без дыр на стыках)
    return 0.001 <= ua <= 0.999 and -0.01 <= ub <= 1.01


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


def is_point_inside_walkable_area(
    x: float,
    y: float,
    rooms: List[Dict[str, Any]],
    corridors: List[Dict[str, Any]],
    tolerance: float = 20.0,
) -> bool:
    """
    Проверяет, находится ли точка внутри доступной зоны (комнаты или коридора).
    Если на этаже не заданы ни комнаты, ни коридоры — возвращает True.
    """
    if not rooms and not corridors:
        return True

    for r in rooms:
        rx = float(r.get("x", 0))
        ry = float(r.get("y", 0))
        rw = float(r.get("width", 0))
        rh = float(r.get("height", 0))
        if (rx - tolerance <= x <= rx + rw + tolerance) and (ry - tolerance <= y <= ry + rh + tolerance):
            return True

    for c in corridors:
        cx1, cy1 = float(c.get("x1", 0)), float(c.get("y1", 0))
        cx2, cy2 = float(c.get("x2", 0)), float(c.get("y2", 0))
        c_width = float(c.get("width", 30))
        if distance_point_to_segment(x, y, cx1, cy1, cx2, cy2) <= (c_width / 2.0 + tolerance):
            return True

    return False


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
        w_p1 = (float(w["x1"]), float(w["y1"]))
        w_p2 = (float(w["x2"]), float(w["y2"]))
        if line_intersection(p1, p2, w_p1, w_p2):
            return False
        # Проверяем расстояние от луча до концов стены (углы и стыки стен толщиной ~6px),
        # если луч не начинается/заканчивается вблизи этого конца
        if math.hypot(p1[0] - w_p1[0], p1[1] - w_p1[1]) > 4.0 and math.hypot(p2[0] - w_p1[0], p2[1] - w_p1[1]) > 4.0:
            if distance_point_to_segment(w_p1[0], w_p1[1], p1[0], p1[1], p2[0], p2[1]) < 3.5:
                return False
        if math.hypot(p1[0] - w_p2[0], p1[1] - w_p2[1]) > 4.0 and math.hypot(p2[0] - w_p2[0], p2[1] - w_p2[1]) > 4.0:
            if distance_point_to_segment(w_p2[0], w_p2[1], p1[0], p1[1], p2[0], p2[1]) < 3.5:
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
        # Проверяем, не лежит ли одна из точек внутри прямоугольного препятствия
        if (rx <= p1[0] <= rx + rw and ry <= p1[1] <= ry + rh) or (
            rx <= p2[0] <= rx + rw and ry <= p2[1] <= ry + rh
        ):
            return False

    return True


def is_segment_walkable(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    rooms: List[Dict[str, Any]],
    corridors: List[Dict[str, Any]],
    tolerance: float = 35.0,
) -> bool:
    """
    Проверяет, что отрезок p1-p2 проходит по доступной площади здания (комнаты или коридоры).
    Если на этаже не заданы ни комнаты, ни коридоры — возвращает True.
    """
    if not rooms and not corridors:
        return True

    dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    steps = max(2, int(dist // 35.0))
    for s in range(1, steps):
        t = s / steps
        sx = p1[0] + (p2[0] - p1[0]) * t
        sy = p1[1] + (p2[1] - p1[1]) * t
        if not is_point_inside_walkable_area(sx, sy, rooms, corridors, tolerance=tolerance):
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
        cx = round(float(x), 1)
        cy = round(float(y), 1)
        # Проверяем существующие узлы в радиусе 12px
        for idx, n in enumerate(nodes):
            if math.hypot(n["x"] - cx, n["y"] - cy) < 12.0:
                return idx
        idx = len(nodes)
        nodes.append({
            "x": cx,
            "y": cy,
            "node_type": node_type,
            "ref": f"auto_{idx}",
        })
        return idx

    def add_edge(idx1: int, idx2: int, force: bool = False) -> None:
        if idx1 == idx2:
            return
        p1 = (nodes[idx1]["x"], nodes[idx1]["y"])
        p2 = (nodes[idx2]["x"], nodes[idx2]["y"])
        if is_segment_clear(p1, p2, walls, circle_obstacles, rect_obstacles):
            if force or is_segment_walkable(p1, p2, rooms, corridors, tolerance=35.0):
                pair = (min(idx1, idx2), max(idx1, idx2))
                edges_set.add(pair)

    # 1. Точки прикрепления для всех POI (поддержка ORM моделей и dict)
    poi_node_indices: List[int] = []
    for poi in pois:
        px = (
            getattr(poi, "x_coord", None)
            or getattr(poi, "x", None)
            or (poi.get("x_coord") if isinstance(poi, dict) else None)
            or (poi.get("x") if isinstance(poi, dict) else 0.0)
        )
        py = (
            getattr(poi, "y_coord", None)
            or getattr(poi, "y", None)
            or (poi.get("y_coord") if isinstance(poi, dict) else None)
            or (poi.get("y") if isinstance(poi, dict) else 0.0)
        )
        cat = (
            getattr(poi, "category", None)
            or (poi.get("category") if isinstance(poi, dict) else "")
        )
        category_val = cat if isinstance(cat, str) else getattr(cat, "value", "")

        node_type = "door" if category_val in ("entrance", "exit") else "walkway"
        poi_idx = add_node(float(px), float(py), node_type=node_type)
        poi_node_indices.append(poi_idx)

    # 2. Узлы и огибание для круглых объектов
    circle_ring_indices: List[List[int]] = []
    for c in circle_obstacles:
        cx, cy, r = c["x"], c["y"], c["radius"]
        clearance = r + 30.0
        ring_indices: List[int] = []
        for k in range(8):
            angle = k * (2 * math.pi / 8)
            bx = cx + clearance * math.cos(angle)
            by = cy + clearance * math.sin(angle)
            n_idx = add_node(bx, by, node_type="walkway")
            ring_indices.append(n_idx)

        for k in range(8):
            add_edge(ring_indices[k], ring_indices[(k + 1) % 8])
        circle_ring_indices.append(ring_indices)

    # 3. Узлы огибания для прямоугольных препятствий
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

    # 3.1. Узлы обхода углов и поворотов стен (без жесткого отсечения по [0, width])
    wall_endpoints: List[Tuple[float, float]] = []
    for w in walls:
        x1, y1 = float(w["x1"]), float(w["y1"])
        x2, y2 = float(w["x2"]), float(w["y2"])
        wall_endpoints.extend([(x1, y1), (x2, y2)])
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length > 1e-3:
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux
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
                if not is_point_inside_walkable_area(bx, by, rooms, corridors, tolerance=25.0):
                    continue
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

    # 3.2. Авто-обнаружение дверных проёмов (проходов между концами стен)
    doorway_node_indices: List[int] = []
    for i, ep1 in enumerate(wall_endpoints):
        for j, ep2 in enumerate(wall_endpoints):
            if i >= j:
                continue
            gap = math.hypot(ep2[0] - ep1[0], ep2[1] - ep1[1])
            # Дверной проём обычно от 25 до 140 пикселей между концами стен
            if 25.0 <= gap <= 140.0:
                door_mid_x = (ep1[0] + ep2[0]) / 2.0
                door_mid_y = (ep1[1] + ep2[1]) / 2.0
                if not is_point_inside_walkable_area(door_mid_x, door_mid_y, rooms, corridors, tolerance=30.0):
                    continue
                door_idx = add_node(door_mid_x, door_mid_y, node_type="door")
                doorway_node_indices.append(door_idx)

    # 4. Узлы для комнат и центров зон (+ внутренняя регулярная сетка для больших зон)
    room_node_indices: List[int] = []
    for room in rooms:
        rx = float(room.get("x", 0))
        ry = float(room.get("y", 0))
        rw = float(room.get("width", 200))
        rh = float(room.get("height", 150))
        if rw <= 0 or rh <= 0:
            continue

        # Центральный узел комнаты
        rc_idx = add_node(rx + rw / 2.0, ry + rh / 2.0, node_type="walkway")
        room_node_indices.append(rc_idx)

        # Сетка внутренних точек для проходимости по всей площади комнаты
        grid_step = 80.0
        num_x = max(1, int(rw // grid_step))
        num_y = max(1, int(rh // grid_step))
        step_x = rw / (num_x + 1)
        step_y = rh / (num_y + 1)

        for ix in range(1, num_x + 1):
            for iy in range(1, num_y + 1):
                sx = rx + ix * step_x
                sy = ry + iy * step_y
                pt_clear = True
                for c in circle_obstacles:
                    if math.hypot(sx - c["x"], sy - c["y"]) <= c["radius"] + 15.0:
                        pt_clear = False
                        break
                if pt_clear:
                    for r_ob in rect_obstacles:
                        if (
                            r_ob["x"] - 8.0 <= sx <= r_ob["x"] + r_ob["width"] + 8.0
                            and r_ob["y"] - 8.0 <= sy <= r_ob["y"] + r_ob["height"] + 8.0
                        ):
                            pt_clear = False
                            break
                if pt_clear:
                    sub_idx = add_node(sx, sy, node_type="walkway")
                    room_node_indices.append(sub_idx)
                    add_edge(rc_idx, sub_idx)

    # 5. Коридоры / проходы
    corridor_node_indices: List[int] = []
    for corr in corridors:
        x1, y1 = float(corr["x1"]), float(corr["y1"])
        x2, y2 = float(corr["x2"]), float(corr["y2"])
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(length // 80))
        prev_idx = add_node(x1, y1, node_type="walkway")
        corridor_node_indices.append(prev_idx)
        for s in range(1, steps + 1):
            t = s / steps
            curr_idx = add_node(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, node_type="walkway")
            corridor_node_indices.append(curr_idx)
            add_edge(prev_idx, curr_idx)
            prev_idx = curr_idx

    # 6. Сетка видимости (Visibility Graph)
    all_key_nodes = list(range(len(nodes)))
    for i in all_key_nodes:
        p1 = (nodes[i]["x"], nodes[i]["y"])
        candidates: List[Tuple[float, int]] = []
        for j in all_key_nodes:
            if i == j:
                continue
            p2 = (nodes[j]["x"], nodes[j]["y"])
            dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if dist <= 550.0:
                candidates.append((dist, j))

        candidates.sort(key=lambda item: item[0])
        connected_count = 0
        for dist, j in candidates:
            if connected_count >= 14:
                break
            p2 = (nodes[j]["x"], nodes[j]["y"])
            if is_segment_clear(p1, p2, walls, circle_obstacles, rect_obstacles):
                add_edge(i, j)
                connected_count += 1

    # Соединяем дверные проёмы и центры комнат со всеми видимыми ключевыми узлами
    cross_room_nodes = doorway_node_indices + room_node_indices + poi_node_indices
    for cr_idx in cross_room_nodes:
        p1 = (nodes[cr_idx]["x"], nodes[cr_idx]["y"])
        for other_idx in cross_room_nodes:
            if cr_idx == other_idx:
                continue
            p2 = (nodes[other_idx]["x"], nodes[other_idx]["y"])
            dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if dist <= 700.0 and is_segment_clear(p1, p2, walls, circle_obstacles, rect_obstacles):
                add_edge(cr_idx, other_idx)

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
                add_edge(poi_idx, best_other, force=True)

    edges_payload = list(edges_set)
    return nodes, edges_payload
