"""
Юнит-тесты генератора человекопонятных инструкций (без БД):
сжатие прямых участков, повороты, развилки, ориентиры, этажи.
"""

import uuid
from typing import Dict, List, Tuple

import pytest

from app.services import route_instructions as instr
from app.services.pathfinder import bearing_deg, euclidean_px

PPM = 100.0  # 100 px = 1 м
F1 = uuid.uuid4()
F2 = uuid.uuid4()
PPM_BY_FLOOR = {F1: PPM, F2: PPM}

POI_ID = uuid.uuid4()
POI_TITLE = "Стенд робототехники"


class N:
    """Тестовая вершина."""

    def __init__(self, x, y):
        self.id = uuid.uuid4()
        self.x = x
        self.y = y


def corridor_leg(a: N, b: N, floor_id=F1, floor_number=1) -> instr.RouteLeg:
    return instr.RouteLeg(
        edge_id=uuid.uuid4(),
        kind="corridor",
        from_node_id=a.id,
        to_node_id=b.id,
        from_x=a.x,
        from_y=a.y,
        to_x=b.x,
        to_y=b.y,
        weight_meters=euclidean_px(a.x, a.y, b.x, b.y) / PPM,
        from_floor_id=floor_id,
        to_floor_id=floor_id,
        from_floor_number=floor_number,
        to_floor_number=floor_number,
    )


def transition_leg(a: N, b: N, kind: str, num_from: int, num_to: int) -> instr.RouteLeg:
    return instr.RouteLeg(
        edge_id=uuid.uuid4(),
        kind=kind,
        from_node_id=a.id,
        to_node_id=b.id,
        from_x=a.x,
        from_y=a.y,
        to_x=b.x,
        to_y=b.y,
        weight_meters=35.0 if kind == "stairs" else 30.0,
        from_floor_id=F1 if num_from == 1 else F2,
        to_floor_id=F1 if num_to == 1 else F2,
        from_floor_number=num_from,
        to_floor_number=num_to,
    )


def bearings(edges: List[Tuple[N, N, uuid.UUID]]) -> Dict[uuid.UUID, List[Tuple[uuid.UUID, float]]]:
    """Азимуты рёбер от вершин — аналог контекста развилок из routing_service."""
    result: Dict[uuid.UUID, List[Tuple[uuid.UUID, float]]] = {}
    for a, b, eid in edges:
        result.setdefault(a.id, []).append((eid, bearing_deg(a.x, a.y, b.x, b.y)))
        result.setdefault(b.id, []).append((eid, bearing_deg(b.x, b.y, a.x, a.y)))
    return result


def build(legs, start: N, poi: N, edges_for_bearings=None, landmarks=None, start_floor=F1):
    return instr.build_steps(
        start_x=start.x,
        start_y=start.y,
        start_floor_id=start_floor,
        legs=legs,
        target_poi_title=POI_TITLE,
        target_poi_x=poi.x,
        target_poi_y=poi.y,
        target_poi_id=POI_ID,
        adjacency_bearings=bearings(edges_for_bearings or []),
        landmarks=landmarks or [],
        ppm_by_floor=PPM_BY_FLOOR,
    )


def kinds(steps):
    return [s.kind for s in steps]


def texts(steps):
    return [s.text for s in steps]


# ---------------------------------------------------------------------------
# Сжатие прямых участков
# ---------------------------------------------------------------------------


def test_collinear_legs_compress_into_single_walk_step():
    a, b, c, d = N(0, 0), N(100, 0), N(200, 0), N(300, 0)
    legs = [corridor_leg(a, b), corridor_leg(b, c), corridor_leg(c, d)]
    steps = build(legs, start=a, poi=d)

    walk_steps = [s for s in steps if s.kind == "walk"]
    assert len(walk_steps) == 1
    assert walk_steps[0].text == "Идите прямо ≈3 м"
    assert walk_steps[0].distance_meters == pytest.approx(3.0)
    assert walk_steps[0].node_ids == [a.id, b.id, c.id, d.id]
    # Финальный шаг — прибытие без дистанции (POI совпадает с вершиной)
    assert steps[-1].kind == "arrival"
    assert steps[-1].text == f"Вы пришли: «{POI_TITLE}»"


def test_gentle_bend_without_fork_is_silently_merged():
    # Изгиб ~8.5° без развилки — инструкция не нужна, участки сливаются
    a, b, c = N(0, 0), N(100, 0), N(200, 15)
    legs = [corridor_leg(a, b), corridor_leg(b, c)]
    e1, e2 = legs[0].edge_id, legs[1].edge_id
    steps = build(legs, start=a, poi=c, edges_for_bearings=[(a, b, e1), (b, c, e2)])

    assert kinds(steps) == ["walk", "arrival"]
    assert steps[0].text == "Идите прямо ≈2 м"


# ---------------------------------------------------------------------------
# Повороты
# ---------------------------------------------------------------------------


def test_right_turn_90_degrees():
    a, b, c = N(0, 0), N(100, 0), N(100, 100)  # восток -> юг = направо
    legs = [corridor_leg(a, b), corridor_leg(b, c)]
    steps = build(legs, start=a, poi=c,
                  edges_for_bearings=[(a, b, legs[0].edge_id), (b, c, legs[1].edge_id)])

    assert kinds(steps) == ["walk", "turn", "walk", "arrival"]
    assert steps[1].text == "Поверните направо"
    assert steps[1].node_ids == [b.id]


def test_left_turn_90_degrees():
    a, b, c = N(0, 0), N(100, 0), N(100, -100)  # восток -> север = налево
    legs = [corridor_leg(a, b), corridor_leg(b, c)]
    steps = build(legs, start=a, poi=c,
                  edges_for_bearings=[(a, b, legs[0].edge_id), (b, c, legs[1].edge_id)])

    assert kinds(steps) == ["walk", "turn", "walk", "arrival"]
    assert steps[1].text == "Поверните налево"


def test_slight_turn_wording():
    a, b, c = N(0, 0), N(100, 0), N(200, 60)  # ~31°
    legs = [corridor_leg(a, b), corridor_leg(b, c)]
    steps = build(legs, start=a, poi=c,
                  edges_for_bearings=[(a, b, legs[0].edge_id), (b, c, legs[1].edge_id)])

    assert kinds(steps) == ["walk", "turn", "walk", "arrival"]
    assert steps[1].text == "Слегка поверните направо"


def test_u_turn_wording():
    a, b, c = N(0, 0), N(100, 0), N(0, 20)  # почти разворот (~169°)
    legs = [corridor_leg(a, b), corridor_leg(b, c)]
    steps = build(legs, start=a, poi=c,
                  edges_for_bearings=[(a, b, legs[0].edge_id), (b, c, legs[1].edge_id)])

    assert any(t == "Развернитесь" for t in texts(steps))


# ---------------------------------------------------------------------------
# Развилки («держитесь левее/правее»)
# ---------------------------------------------------------------------------


def test_keep_instruction_at_confusing_fork():
    """
    Идём почти прямо (A->B->C, отклонение ~6°), но из B уходит похожее
    ребро B->D (всего ~8° правее нашего пути) — его легко перепутать.
    Ожидаем предупреждение «Держитесь левее».
    """
    a, b, c, d = N(0, 0), N(100, 0), N(200, 10), N(200, 25)
    legs = [corridor_leg(a, b), corridor_leg(b, c)]
    fork_edge_id = uuid.uuid4()
    edges = [
        (a, b, legs[0].edge_id),
        (b, c, legs[1].edge_id),
        (b, d, fork_edge_id),
    ]
    steps = build(legs, start=a, poi=c, edges_for_bearings=edges)

    assert kinds(steps) == ["walk", "keep", "walk", "arrival"]
    assert steps[1].text == "Держитесь левее, не сворачивая в ответвление"
    assert steps[1].node_ids == [b.id]


def test_no_keep_instruction_when_fork_is_clearly_divergent():
    # Ребро-ответвление уходит под 70° — перепутать сложно, молчим
    a, b, c, d = N(0, 0), N(100, 0), N(200, 10), N(150, 140)
    legs = [corridor_leg(a, b), corridor_leg(b, c)]
    edges = [
        (a, b, legs[0].edge_id),
        (b, c, legs[1].edge_id),
        (b, d, uuid.uuid4()),
    ]
    steps = build(legs, start=a, poi=c, edges_for_bearings=edges)

    assert kinds(steps) == ["walk", "arrival"]


# ---------------------------------------------------------------------------
# Ориентиры (landmark вместо метров)
# ---------------------------------------------------------------------------


def test_landmark_replaces_distance_when_near_segment_end():
    a, b = N(0, 0), N(1500, 0)  # 15 м прямо
    lm = instr.Landmark(
        id=uuid.uuid4(), title="Стойка регистрации",
        x=1520, y=100, floor_id=F1,  # 1 м от конца, далеко от начала; юг = справа
    )
    steps = build([corridor_leg(a, b)], start=a, poi=b, landmarks=[lm])

    assert steps[0].kind == "walk"
    assert steps[0].text == "Идите прямо, пока не увидите справа «Стойка регистрации»"


def test_landmark_on_the_left_side():
    a, b = N(0, 0), N(1500, 0)
    lm = instr.Landmark(
        id=uuid.uuid4(), title="Гардероб",
        x=1480, y=-120, floor_id=F1,  # север = слева
    )
    steps = build([corridor_leg(a, b)], start=a, poi=b, landmarks=[lm])
    assert steps[0].text == "Идите прямо, пока не увидите слева «Гардероб»"


def test_landmark_rejected_when_equally_close_to_start():
    a, b = N(0, 0), N(1500, 0)
    lm = instr.Landmark(
        id=uuid.uuid4(), title="Кафе",
        x=100, y=100, floor_id=F1,  # рядом со стартом, а не с концом
    )
    steps = build([corridor_leg(a, b)], start=a, poi=b, landmarks=[lm])
    assert steps[0].text == "Идите прямо ≈15 м"


def test_landmark_rejected_when_too_far_from_end():
    a, b = N(0, 0), N(1500, 0)
    lm = instr.Landmark(
        id=uuid.uuid4(), title="Туалет",
        x=600, y=50, floor_id=F1,  # 9 м до конца — за пределами радиуса
    )
    steps = build([corridor_leg(a, b)], start=a, poi=b, landmarks=[lm])
    assert steps[0].text == "Идите прямо ≈15 м"


def test_target_poi_is_not_used_as_landmark():
    a, b = N(0, 0), N(500, 0)
    target_lm = instr.Landmark(id=POI_ID, title=POI_TITLE, x=510, y=20, floor_id=F1)
    steps = build([corridor_leg(a, b)], start=a, poi=b, landmarks=[target_lm])
    assert steps[0].text == "Идите прямо ≈5 м"


# ---------------------------------------------------------------------------
# Межэтажные переходы
# ---------------------------------------------------------------------------


def test_stairs_up_instruction():
    a, s1, s2, b = N(0, 0), N(100, 0), N(100, 0), N(200, 0)
    legs = [
        corridor_leg(a, s1),
        transition_leg(s1, s2, "stairs", num_from=1, num_to=2),
        corridor_leg(s2, b, floor_id=F2, floor_number=2),
    ]
    steps = build(legs, start=a, poi=b)

    assert kinds(steps) == ["walk", "stairs", "walk", "arrival"]
    assert steps[1].text == "Поднимитесь по лестнице на 2 этаж"
    assert steps[1].node_ids == [s1.id, s2.id]


def test_elevator_down_instruction():
    a, e2, e1, b = N(0, 0), N(100, 0), N(100, 0), N(200, 0)
    legs = [
        corridor_leg(a, e2, floor_id=F2, floor_number=2),
        transition_leg(e2, e1, "elevator", num_from=2, num_to=1),
        corridor_leg(e1, b),
    ]
    steps = build(legs, start=a, poi=b, start_floor=F2)

    assert kinds(steps) == ["walk", "elevator", "walk", "arrival"]
    assert steps[1].text == "Спуститесь на лифте на 1 этаж"


# ---------------------------------------------------------------------------
# Подход к стартовой вершине и сход к цели
# ---------------------------------------------------------------------------


def test_approach_step_when_start_point_is_far_from_graph():
    start = N(0, 300)  # 3 м до ближайшей вершины A(0,0)
    a, b = N(0, 0), N(100, 0)
    steps = build([corridor_leg(a, b)], start=start, poi=b)

    assert steps[0].kind == "approach"
    assert steps[0].text == "Пройдите ≈3 м до начала маршрута"
    assert steps[0].node_ids == [a.id]


def test_no_approach_step_when_start_is_close():
    start = N(0, 50)  # 0.5 м — не озвучиваем
    a, b = N(0, 0), N(100, 0)
    steps = build([corridor_leg(a, b)], start=start, poi=b)
    assert kinds(steps)[0] == "walk"


def test_arrival_with_walkoff_distance():
    a, b = N(0, 0), N(100, 0)
    poi = N(300, 0)  # 2 м от последней вершины
    steps = build([corridor_leg(a, b)], start=a, poi=poi)

    assert steps[-1].kind == "arrival"
    assert steps[-1].text == f"Пройдите ≈2 м — вы у цели: «{POI_TITLE}»"


def test_empty_legs_direct_walk_to_poi():
    start = N(0, 0)
    poi = N(250, 0)
    steps = build([], start=start, poi=poi)

    assert kinds(steps) == ["walk"]
    assert steps[0].text == f"Идите к «{POI_TITLE}» (≈2 м)"
