"""
Автоматическая генерация навигационного графа на бэкенде.

Строит проходимый граф путей по 2D-планировке помещения (комнаты, коридоры,
стены, круглые и прямоугольные объекты/препятствия) и точкам интереса (POI).

Учитывает:
- Точки прикрепления для POI (входы, лавочки, урны, торговые точки, стенды).
- Огибание углов стен и прямоугольных препятствий с безопасным отступом.
- Огибание круглых объектов (колонны, круглые стенды/островки) по касательным точкам обхода.
- Повороты коридоров и пересечения проходов.
- Изоляция комнат: узлы внутри разных комнат не соединяются напрямую,
  переходы между помещениями возможны только через двери и коридоры.
- Строгая локализация: узлы не выходят наружу здания в пустоту.
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


def point_in_polygon(x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
    """Проверяет попадание точки (x, y) внутрь произвольного многоугольника poly (ray casting)."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def find_room_for_point(
    x: float,
    y: float,
    rooms: List[Dict[str, Any]],
    tolerance: float = 1.0,
) -> Optional[str]:
    """Возвращает идентификатор комнаты (id или title/ref), содержащей точку."""
    for idx, r in enumerate(rooms):
        rx, ry = float(r.get("x", 0)), float(r.get("y", 0))
        rw, rh = float(r.get("width", 0)), float(r.get("height", 0))
        room_id = str(r.get("id") or r.get("title") or f"room_{idx}")
        points = r.get("points")
        if points and len(points) >= 3:
            poly = [(float(p[0]), float(p[1])) for p in points]
            if point_in_polygon(x, y, poly):
                return room_id
        elif (rx - tolerance <= x <= rx + rw + tolerance) and (ry - tolerance <= y <= ry + rh + tolerance):
            return room_id
    return None


def find_rooms_near_point(
    x: float,
    y: float,
    rooms: List[Dict[str, Any]],
    distance: float = 35.0,
) -> Set[str]:
    """Возвращает набор идентификаторов комнат, к которым прилегает точка (на расстоянии <= distance)."""
    result: Set[str] = set()
    for idx, r in enumerate(rooms):
        rx, ry = float(r.get("x", 0)), float(r.get("y", 0))
        rw, rh = float(r.get("width", 0)), float(r.get("height", 0))
        room_id = str(r.get("id") or r.get("title") or f"room_{idx}")
        dx = max(rx - x, 0.0, x - (rx + rw))
        dy = max(ry - y, 0.0, y - (ry + rh))
        if math.hypot(dx, dy) <= distance:
            result.add(room_id)
    return result


def is_point_inside_walkable_area(
    x: float,
    y: float,
    rooms: List[Dict[str, Any]],
    corridors: List[Dict[str, Any]],
    tolerance: float = 2.0,
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
        points = r.get("points")
        if points and len(points) >= 3:
            poly = [(float(p[0]), float(p[1])) for p in points]
            if point_in_polygon(x, y, poly):
                return True
        elif (rx - tolerance <= x <= rx + rw + tolerance) and (ry - tolerance <= y <= ry + rh + tolerance):
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
    tolerance: float = 5.0,
) -> bool:
    """
    Проверяет, что отрезок p1-p2 проходит по доступной площади здания (комнаты или коридоры).
    Если на этаже не заданы ни комнаты, ни коридоры — возвращает True.
    """
    if not rooms and not corridors:
        return True

    dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    steps = max(2, int(dist // 25.0))
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
      - nodes_payload: список словарей узлов {'x', 'y', 'node_type', 'ref', 'room_id'}
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
    door_adjacent_rooms: Dict[int, Set[str]] = {}

    def add_node(
        x: float,
        y: float,
        node_type: str = "walkway",
        room_id: Optional[str] = None,
        force_inside: bool = False,
    ) -> int:
        cx = round(float(x), 1)
        cy = round(float(y), 1)

        # 1. Строгая проверка нахождения внутри здания:
        # Узлы не должны генерироваться в пустоте за пределами комнат и коридоров.
        if (rooms or corridors) and not force_inside:
            if not is_point_inside_walkable_area(cx, cy, rooms, corridors, tolerance=2.0):
                return -1

        # Если room_id не передан явно и это не дверь/коридор, определяем комнату по координатам
        if room_id is None and node_type not in ("door", "corridor"):
            room_id = find_room_for_point(cx, cy, rooms, tolerance=2.0)

        # Проверяем существующие узлы в радиусе 12px
        for idx, n in enumerate(nodes):
            if math.hypot(n["x"] - cx, n["y"] - cy) < 12.0:
                if node_type == "door":
                    n["node_type"] = "door"
                    n["room_id"] = None
                elif room_id and not n.get("room_id") and n.get("node_type") != "door":
                    n["room_id"] = room_id
                return idx

        idx = len(nodes)
        nodes.append({
            "x": cx,
            "y": cy,
            "node_type": node_type,
            "ref": f"auto_{idx}",
            "room_id": room_id,
        })
        return idx

    def add_edge(idx1: int, idx2: int, force: bool = False) -> None:
        if idx1 == idx2 or idx1 < 0 or idx2 < 0 or idx1 >= len(nodes) or idx2 >= len(nodes):
            return

        n1 = nodes[idx1]
        n2 = nodes[idx2]

        if not force:
            r1 = n1.get("room_id")
            r2 = n2.get("room_id")
            # ПРАВИЛО 1: Узлы разных комнат не могут соединяться напрямую!
            if r1 and r2 and r1 != r2:
                return

            # ПРАВИЛО 2: Дверной узел может соединяться только с узлами прилегающих к нему комнат
            for d_idx, o_idx in [(idx1, idx2), (idx2, idx1)]:
                if d_idx in door_adjacent_rooms:
                    allowed_rooms = door_adjacent_rooms[d_idx]
                    o_room = nodes[o_idx].get("room_id")
                    if o_room is not None and o_room not in allowed_rooms:
                        return
                    if o_idx in door_adjacent_rooms:
                        other_allowed = door_adjacent_rooms[o_idx]
                        if not (allowed_rooms & other_allowed):
                            d_dist = math.hypot(n1["x"] - n2["x"], n1["y"] - n2["y"])
                            if d_dist > 120.0:
                                return

        p1 = (n1["x"], n1["y"])
        p2 = (n2["x"], n2["y"])
        if is_segment_clear(p1, p2, walls, circle_obstacles, rect_obstacles):
            if force or is_segment_walkable(p1, p2, rooms, corridors, tolerance=5.0):
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
        poi_room = find_room_for_point(float(px), float(py), rooms, tolerance=10.0)
        poi_idx = add_node(float(px), float(py), node_type=node_type, room_id=poi_room, force_inside=True)
        if poi_idx != -1:
            poi_node_indices.append(poi_idx)
            if node_type == "door":
                adj = find_rooms_near_point(float(px), float(py), rooms, distance=40.0)
                if adj:
                    door_adjacent_rooms[poi_idx] = adj

    # 2. Сбор концов стен и авто-обнаружение дверных проёмов (проходов между концами разных стен)
    wall_endpoints_with_id: List[Tuple[Tuple[float, float], int]] = []
    for w_idx, w in enumerate(walls):
        x1, y1 = float(w["x1"]), float(w["y1"])
        x2, y2 = float(w["x2"]), float(w["y2"])
        wall_endpoints_with_id.append(((x1, y1), w_idx))
        wall_endpoints_with_id.append(((x2, y2), w_idx))

    doorway_node_indices: List[int] = []
    for i, (ep1, w1) in enumerate(wall_endpoints_with_id):
        for j, (ep2, w2) in enumerate(wall_endpoints_with_id):
            if i >= j or w1 == w2:
                continue
            gap = math.hypot(ep2[0] - ep1[0], ep2[1] - ep1[1])
            # Дверной проём обычно от 25 до 140 пикселей между концами разных стен
            if 25.0 <= gap <= 140.0:
                door_mid_x = (ep1[0] + ep2[0]) / 2.0
                door_mid_y = (ep1[1] + ep2[1]) / 2.0
                if not is_point_inside_walkable_area(door_mid_x, door_mid_y, rooms, corridors, tolerance=3.0):
                    continue
                on_wall = any(
                    distance_point_to_segment(door_mid_x, door_mid_y, float(w["x1"]), float(w["y1"]), float(w["x2"]), float(w["y2"])) < 5.0
                    for w in walls
                )
                if on_wall:
                    continue
                door_idx = add_node(door_mid_x, door_mid_y, node_type="door", room_id=None)
                if door_idx != -1:
                    door_adjacent_rooms[door_idx] = find_rooms_near_point(door_mid_x, door_mid_y, rooms, distance=35.0)
                    if door_idx not in doorway_node_indices:
                        doorway_node_indices.append(door_idx)

    # 3. Проходы между смежными открытыми зонами (соприкасающиеся комнаты без стены)
    for idx_a, ra in enumerate(rooms):
        for idx_b, rb in enumerate(rooms):
            if idx_a >= idx_b:
                continue
            ax, ay = float(ra.get("x", 0)), float(ra.get("y", 0))
            aw, ah = float(ra.get("width", 0)), float(ra.get("height", 0))
            bx, by = float(rb.get("x", 0)), float(rb.get("y", 0))
            bw, bh = float(rb.get("width", 0)), float(rb.get("height", 0))

            # Соприкосновение по вертикали
            if abs((ax + aw) - bx) <= 4.0 or abs((bx + bw) - ax) <= 4.0:
                oy1 = max(ay, by)
                oy2 = min(ay + ah, by + bh)
                if oy2 - oy1 >= 30.0:
                    mx = (ax + aw + bx) / 2.0 if abs((ax + aw) - bx) <= 4.0 else (bx + bw + ax) / 2.0
                    my = (oy1 + oy2) / 2.0
                    if not any(distance_point_to_segment(mx, my, float(w["x1"]), float(w["y1"]), float(w["x2"]), float(w["y2"])) < 5.0 for w in walls):
                        trans_idx = add_node(mx, my, node_type="door", room_id=None)
                        if trans_idx != -1:
                            ra_id = str(ra.get("id") or ra.get("title") or f"room_{idx_a}")
                            rb_id = str(rb.get("id") or rb.get("title") or f"room_{idx_b}")
                            door_adjacent_rooms[trans_idx] = {ra_id, rb_id}
                            if trans_idx not in doorway_node_indices:
                                doorway_node_indices.append(trans_idx)

            # Соприкосновение по горизонтали
            if abs((ay + ah) - by) <= 4.0 or abs((by + bh) - ay) <= 4.0:
                ox1 = max(ax, bx)
                ox2 = min(ax + aw, bx + bw)
                if ox2 - ox1 >= 30.0:
                    my = (ay + ah + by) / 2.0 if abs((ay + ah) - by) <= 4.0 else (by + bh + ay) / 2.0
                    mx = (ox1 + ox2) / 2.0
                    if not any(distance_point_to_segment(mx, my, float(w["x1"]), float(w["y1"]), float(w["x2"]), float(w["y2"])) < 5.0 for w in walls):
                        trans_idx = add_node(mx, my, node_type="door", room_id=None)
                        if trans_idx != -1:
                            ra_id = str(ra.get("id") or ra.get("title") or f"room_{idx_a}")
                            rb_id = str(rb.get("id") or rb.get("title") or f"room_{idx_b}")
                            door_adjacent_rooms[trans_idx] = {ra_id, rb_id}
                            if trans_idx not in doorway_node_indices:
                                doorway_node_indices.append(trans_idx)

    # 4. Узлы и огибание для круглых объектов
    circle_ring_indices: List[List[int]] = []
    for c in circle_obstacles:
        cx, cy, r = c["x"], c["y"], c["radius"]
        c_room = find_room_for_point(cx, cy, rooms, tolerance=2.0)
        clearance = r + 25.0
        in_walkable = is_point_inside_walkable_area(cx, cy, rooms, corridors, tolerance=30.0)
        ring_indices: List[int] = []
        for k in range(8):
            angle = k * (2 * math.pi / 8)
            bx = cx + clearance * math.cos(angle)
            by = cy + clearance * math.sin(angle)
            n_idx = add_node(bx, by, node_type="walkway", room_id=c_room, force_inside=in_walkable)
            if n_idx != -1:
                ring_indices.append(n_idx)

        for k in range(len(ring_indices)):
            add_edge(ring_indices[k], ring_indices[(k + 1) % len(ring_indices)], force=True)
        circle_ring_indices.append(ring_indices)

    # 5. Узлы огибания для прямоугольных препятствий
    rect_corner_indices: List[List[int]] = []
    for r in rect_obstacles:
        rx, ry, rw, rh = r["x"], r["y"], r["width"], r["height"]
        r_room = find_room_for_point(rx + rw / 2.0, ry + rh / 2.0, rooms, tolerance=2.0)
        margin = 25.0
        corners = [
            (rx - margin, ry - margin),
            (rx + rw + margin, ry - margin),
            (rx + rw + margin, ry + rh + margin),
            (rx - margin, ry + rh + margin),
        ]
        in_walkable = is_point_inside_walkable_area(rx + rw / 2.0, ry + rh / 2.0, rooms, corridors, tolerance=30.0)
        c_indices = [
            idx for idx in (add_node(x, y, node_type="walkway", room_id=r_room, force_inside=in_walkable) for x, y in corners)
            if idx != -1
        ]
        for k in range(len(c_indices)):
            add_edge(c_indices[k], c_indices[(k + 1) % len(c_indices)], force=True)
        rect_corner_indices.append(c_indices)

    # 6. Узлы обхода углов и поворотов стен
    for w in walls:
        x1, y1 = float(w["x1"]), float(w["y1"])
        x2, y2 = float(w["x2"]), float(w["y2"])
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length > 1e-3:
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux
            margin = 25.0
            wall_bypasses = [
                (x1 - margin * ux, y1 - margin * uy),
                (x1 + margin * nx, y1 + margin * ny),
                (x1 - margin * nx, y1 - margin * ny),
                (x2 + margin * ux, y2 + margin * uy),
                (x2 + margin * nx, y2 + margin * ny),
                (x2 - margin * nx, y2 - margin * ny),
            ]
            for bx, by in wall_bypasses:
                # Если в пределах 15px уже есть дверной узел, не дублируем его
                if any(math.hypot(bx - nodes[d]["x"], by - nodes[d]["y"]) < 15.0 for d in doorway_node_indices):
                    continue
                b_room = find_room_for_point(bx, by, rooms, tolerance=2.0)
                if (rooms or corridors) and b_room is None and not is_point_inside_walkable_area(bx, by, [], corridors, tolerance=2.0):
                    continue
                clear_point = True
                for c in circle_obstacles:
                    if math.hypot(bx - c["x"], by - c["y"]) <= c["radius"] + 10.0:
                        clear_point = False
                        break
                if clear_point:
                    for r_ob in rect_obstacles:
                        if (
                            r_ob["x"] - 5.0 <= bx <= r_ob["x"] + r_ob["width"] + 5.0
                            and r_ob["y"] - 5.0 <= by <= r_ob["y"] + r_ob["height"] + 5.0
                        ):
                            clear_point = False
                            break
                if clear_point:
                    add_node(bx, by, node_type="walkway", room_id=b_room)

    # 4. Узлы для комнат и центров зон (+ внутренняя регулярная сетка для больших зон)
    room_node_indices: List[int] = []
    for idx_r, room in enumerate(rooms):
        rx = float(room.get("x", 0))
        ry = float(room.get("y", 0))
        rw = float(room.get("width", 200))
        rh = float(room.get("height", 150))
        if rw <= 0 or rh <= 0:
            continue
        r_id = str(room.get("id") or room.get("title") or f"room_{idx_r}")

        # Центральный узел комнаты
        rc_idx = add_node(rx + rw / 2.0, ry + rh / 2.0, node_type="walkway", room_id=r_id)
        if rc_idx != -1:
            room_node_indices.append(rc_idx)

        # Сетка внутренних точек для проходимости по всей площади комнаты
        grid_step = 80.0
        num_x = max(1, int(rw // grid_step))
        num_y = max(1, int(rh // grid_step))
        step_x = rw / (num_x + 1)
        step_y = rh / (num_y + 1)
        grid_indices: Dict[Tuple[int, int], int] = {}

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
                    sub_idx = add_node(sx, sy, node_type="walkway", room_id=r_id)
                    if sub_idx != -1:
                        grid_indices[(ix, iy)] = sub_idx
                        room_node_indices.append(sub_idx)
                        add_edge(rc_idx, sub_idx)
                        for dx, dy in [(-1, 0), (0, -1), (-1, -1), (1, -1)]:
                            neighbor = grid_indices.get((ix + dx, iy + dy))
                            if neighbor is not None:
                                add_edge(sub_idx, neighbor)

    # 5. Коридоры / проходы
    corridor_node_indices: List[int] = []
    for corr in corridors:
        x1, y1 = float(corr["x1"]), float(corr["y1"])
        x2, y2 = float(corr["x2"]), float(corr["y2"])
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(length // 80))
        prev_idx = add_node(x1, y1, node_type="walkway", room_id=None)
        if prev_idx != -1:
            corridor_node_indices.append(prev_idx)
        for s in range(1, steps + 1):
            t = s / steps
            curr_idx = add_node(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, node_type="walkway", room_id=None)
            if curr_idx != -1:
                corridor_node_indices.append(curr_idx)
                if prev_idx != -1:
                    add_edge(prev_idx, curr_idx)
                prev_idx = curr_idx

    # 6. Соединяем дверные проёмы с видимыми узлами прилегающих зон (до 320px)
    for d_idx in doorway_node_indices:
        p_d = (nodes[d_idx]["x"], nodes[d_idx]["y"])
        candidates: List[Tuple[float, int]] = []
        for o_idx in range(len(nodes)):
            if o_idx == d_idx:
                continue
            p_o = (nodes[o_idx]["x"], nodes[o_idx]["y"])
            dist = math.hypot(p_o[0] - p_d[0], p_o[1] - p_d[1])
            if dist <= 320.0:
                candidates.append((dist, o_idx))
        candidates.sort(key=lambda item: item[0])
        for dist, o_idx in candidates[:10]:
            add_edge(d_idx, o_idx)

    # 7. Соединяем коридорные узлы с близкими дверями и коридорами (до 220px)
    for c_idx in corridor_node_indices:
        p_c = (nodes[c_idx]["x"], nodes[c_idx]["y"])
        for d_idx in doorway_node_indices:
            p_d = (nodes[d_idx]["x"], nodes[d_idx]["y"])
            if math.hypot(p_d[0] - p_c[0], p_d[1] - p_c[1]) <= 220.0:
                add_edge(c_idx, d_idx)

    # 8. Соединяем POI с ближайшими видимыми узлами
    for poi_idx in poi_node_indices:
        p_poi = (nodes[poi_idx]["x"], nodes[poi_idx]["y"])
        candidates = []
        for o_idx in range(len(nodes)):
            if o_idx == poi_idx:
                continue
            p_o = (nodes[o_idx]["x"], nodes[o_idx]["y"])
            dist = math.hypot(p_o[0] - p_poi[0], p_o[1] - p_poi[1])
            if dist <= 350.0:
                candidates.append((dist, o_idx))
        candidates.sort(key=lambda item: item[0])
        for dist, o_idx in candidates[:6]:
            add_edge(poi_idx, o_idx)

    # 9. Локальная видимость внутри комнат и коридоров (до 180px)
    for i in range(len(nodes)):
        p1 = (nodes[i]["x"], nodes[i]["y"])
        candidates = []
        for j in range(i + 1, len(nodes)):
            p2 = (nodes[j]["x"], nodes[j]["y"])
            dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if dist <= 180.0:
                candidates.append((dist, j))
        candidates.sort(key=lambda item: item[0])
        for dist, j in candidates[:5]:
            add_edge(i, j)

    # 10. Гарантируем, что каждая POI соединена хотя бы с 1 ближайшим видимым узлом
    for poi_idx in poi_node_indices:
        has_edge = any(poi_idx in e for e in edges_set)
        if not has_edge:
            closest_dist = float("inf")
            best_other = None
            p_poi = (nodes[poi_idx]["x"], nodes[poi_idx]["y"])
            poi_room = nodes[poi_idx].get("room_id")
            for other_idx in range(len(nodes)):
                if other_idx == poi_idx:
                    continue
                other_room = nodes[other_idx].get("room_id")
                if poi_room and other_room and poi_room != other_room:
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
