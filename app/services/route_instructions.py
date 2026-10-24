"""
Генерация человекопонятных пошаговых инструкций по найденному маршруту.

Чистый модуль (без БД/FastAPI): принимает геометрию пути и контекст
(развилки, POI-ориентиры) и возвращает список шагов на русском языке.

Общий алгоритм:
1. Сжатие: последовательные коридорные рёбра, идущие почти по прямой,
   объединяются в одну инструкцию «Идите прямо ...».
2. Повороты: классифицируются по углу между рёбрами; рёбра-«конкуренты»
   на развилке (уходящие под близким углом к нашему пути) повышают
   важность инструкции — там, где пользователь может перепутать проход,
   выдаётся «Держитесь левее/правее», а где развилки нет и изгиб плавный —
   инструкция подавляется вовсе.
3. Ориентиры: если у конца сжатого участка есть POI, заметно более близкий
   к концу участка, чем к его началу, инструкция привязывается к нему:
   «Идите прямо, пока не увидите справа «Стенд робототехники»».
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.pathfinder import bearing_deg, euclidean_px, signed_turn_deg, turn_side

# ---------------------------------------------------------------------------
# Пороговые константы алгоритма (подобраны эвристически)
# ---------------------------------------------------------------------------

#: Поворот меньше этого угла считается движением «прямо» (участки сливаются).
STRAIGHT_MERGE_MAX_DEG: float = 25.0
#: Верхняя граница «слегка поверните / держитесь».
SLIGHT_TURN_MAX_DEG: float = 60.0
#: Нижняя граница «резко поверните».
SHARP_TURN_MIN_DEG: float = 120.0
#: Выше этого угла — «развернитесь».
U_TURN_MIN_DEG: float = 160.0
#: Ребро развилки в пределах этого угла от нашего пути можно перепутать с ним.
FORK_CONFUSION_DEG: float = 45.0
#: Максимальное расстояние от POI-ориентира до конца участка (метры).
LANDMARK_RADIUS_M: float = 8.0
#: Во сколько раз ориентир должен быть ближе к концу участка, чем к началу.
LANDMARK_CLOSER_RATIO: float = 1.5
#: Подход к стартовой вершине короче этого расстояния не озвучивается.
MIN_APPROACH_DIST_M: float = 1.0


# ---------------------------------------------------------------------------
# Входные структуры
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteLeg:
    """Одно пройденное ребро маршрута с геометрией и контекстом этажей."""

    edge_id: uuid.UUID
    kind: str  # "corridor" | "stairs" | "elevator"
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    weight_meters: float
    from_floor_id: uuid.UUID
    to_floor_id: uuid.UUID
    from_floor_number: int
    to_floor_number: int

    @property
    def floor_id(self) -> uuid.UUID:
        """Этаж, на котором происходит движение по ребру."""
        return self.from_floor_id


@dataclass(frozen=True)
class Landmark:
    """POI-ориентир на этаже."""

    id: uuid.UUID
    title: str
    x: float
    y: float
    floor_id: uuid.UUID


@dataclass
class StepDraft:
    """Готовый шаг инструкции (до упаковки в Pydantic-схему)."""

    kind: str  # approach | walk | turn | keep | stairs | elevator | arrival
    text: str
    distance_meters: Optional[float] = None
    node_ids: List[uuid.UUID] = field(default_factory=list)
    floor_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# Вспомогательные функции текста
# ---------------------------------------------------------------------------


def _fmt_meters(distance_m: float) -> str:
    """Форматирует расстояние для подсказки: «≈13 м» (минимум 1 м)."""
    return f"≈{max(1, round(distance_m))} м"


def _turn_wording(delta_deg: float, has_fork_confusion: bool) -> Tuple[str, str]:
    """
    Подбирает формулировку поворота по знаковому углу.

    Возвращает (kind, text): kind = "keep" | "turn".
    Положительный delta_deg = поворот направо (ось Y вниз).
    """
    abs_delta = abs(delta_deg)
    side_word = "направо" if delta_deg > 0 else "налево"

    if abs_delta < SLIGHT_TURN_MAX_DEG:
        if has_fork_confusion:
            # На развилке плавное отклонение надёжнее описать как «держитесь»
            keep_side = "правее" if delta_deg > 0 else "левее"
            return "keep", f"Держитесь {keep_side}"
        return "turn", f"Слегка поверните {side_word}"
    if abs_delta < SHARP_TURN_MIN_DEG:
        return "turn", f"Поверните {side_word}"
    if abs_delta < U_TURN_MIN_DEG:
        return "turn", f"Резко поверните {side_word}"
    return "turn", "Развернитесь"


def _confusing_edge_side(
    out_bearing: float, other_bearings: Sequence[float]
) -> Optional[str]:
    """
    Проверяет, есть ли на развилке ребро, которое можно перепутать с нашим
    (уходящее под углом < FORK_CONFUSION_DEG от нашего направления).

    Возвращает сторону, которой следует держаться ("left"/"right"), чтобы
    не свернуть на ближайшее такое ребро, или None.
    """
    best_delta: Optional[float] = None
    for other in other_bearings:
        delta = signed_turn_deg(out_bearing, other)
        if abs(delta) < FORK_CONFUSION_DEG and (
            best_delta is None or abs(delta) < abs(best_delta)
        ):
            best_delta = delta
    if best_delta is None:
        return None
    # Конкурент справа от нашего пути (delta > 0) — держимся левее, и наоборот.
    return "left" if best_delta > 0 else "right"


def _find_landmark(
    group: Sequence[RouteLeg],
    landmarks: Sequence[Landmark],
    ppm: float,
    exclude_id: Optional[uuid.UUID],
) -> Optional[Tuple[Landmark, str]]:
    """
    Ищет POI-ориентир для сжатого участка: на том же этаже, в радиусе
    LANDMARK_RADIUS_M от конца участка и заметно (в LANDMARK_CLOSER_RATIO
    раза) ближе к концу, чем к началу. Возвращает (ориентир, сторона).
    """
    if not group:
        return None
    start_x, start_y = group[0].from_x, group[0].from_y
    end_leg = group[-1]
    end_x, end_y = end_leg.to_x, end_leg.to_y
    floor_id = end_leg.floor_id
    radius_px = LANDMARK_RADIUS_M * ppm

    best: Optional[Tuple[Landmark, float]] = None
    for lm in landmarks:
        if lm.floor_id != floor_id or lm.id == exclude_id:
            continue
        dist_end = euclidean_px(lm.x, lm.y, end_x, end_y)
        if dist_end > radius_px:
            continue
        dist_start = euclidean_px(lm.x, lm.y, start_x, start_y)
        if dist_start < dist_end * LANDMARK_CLOSER_RATIO:
            continue
        if best is None or dist_end < best[1]:
            best = (lm, dist_end)
    if best is None:
        return None
    lm = best[0]
    side = turn_side(end_leg.from_x, end_leg.from_y, end_x, end_y, lm.x, lm.y)
    return lm, side


# ---------------------------------------------------------------------------
# Основной алгоритм
# ---------------------------------------------------------------------------


def build_steps(
    start_x: float,
    start_y: float,
    start_floor_id: uuid.UUID,
    legs: Sequence[RouteLeg],
    target_poi_title: str,
    target_poi_x: float,
    target_poi_y: float,
    target_poi_id: uuid.UUID,
    adjacency_bearings: Dict[uuid.UUID, List[Tuple[uuid.UUID, float]]],
    landmarks: Sequence[Landmark],
    ppm_by_floor: Dict[uuid.UUID, float],
) -> List[StepDraft]:
    """
    Строит пошаговую инструкцию по маршруту.

    :param start_x/start_y: точка «А» (пиксели плана start_floor_id).
    :param legs: упорядоченные рёбра пути (может быть пусто — цель на том
        же ребре, что и старт).
    :param adjacency_bearings: node_id -> [(edge_id, азимут от вершины)],
        только коридорные рёбра — для анализа развилок.
    :param landmarks: POI всех задействованных этажей (ориентиры).
    :param ppm_by_floor: масштаб каждого этажа (px на метр).
    """
    steps: List[StepDraft] = []

    # --- Особый случай: путь без рёбер (старт и цель проецируются на одно
    # и то же ребро — идём напрямую вдоль него) ---
    if not legs:
        dist_m = euclidean_px(start_x, start_y, target_poi_x, target_poi_y) / ppm_by_floor[
            start_floor_id
        ]
        steps.append(
            StepDraft(
                kind="walk",
                text=f"Идите к «{target_poi_title}» ({_fmt_meters(dist_m)})",
                distance_meters=dist_m,
                floor_id=start_floor_id,
            )
        )
        return steps

    # --- Шаг 0: подход к стартовой вершине графа ---
    first = legs[0]
    approach_m = (
        euclidean_px(start_x, start_y, first.from_x, first.from_y)
        / ppm_by_floor[first.floor_id]
    )
    if approach_m >= MIN_APPROACH_DIST_M:
        steps.append(
            StepDraft(
                kind="approach",
                text=f"Пройдите {_fmt_meters(approach_m)} до начала маршрута",
                distance_meters=approach_m,
                node_ids=[first.from_node_id],
                floor_id=first.floor_id,
            )
        )

    # --- Проход по рёбрам со сжатием прямых участков ---
    corridor_group: List[RouteLeg] = []

    def flush_group() -> None:
        """Завершает накопленный прямолинейный участок и emits walk-шаг."""
        if not corridor_group:
            return
        dist_m = sum(leg.weight_meters for leg in corridor_group)
        ppm = ppm_by_floor[corridor_group[0].floor_id]
        landmark = _find_landmark(corridor_group, landmarks, ppm, exclude_id=target_poi_id)
        if landmark is not None:
            lm, side = landmark
            side_word = "справа" if side == "right" else "слева"
            text = f"Идите прямо, пока не увидите {side_word} «{lm.title}»"
        else:
            text = f"Идите прямо {_fmt_meters(dist_m)}"
        node_ids = [corridor_group[0].from_node_id] + [
            leg.to_node_id for leg in corridor_group
        ]
        steps.append(
            StepDraft(
                kind="walk",
                text=text,
                distance_meters=dist_m,
                node_ids=node_ids,
                floor_id=corridor_group[0].floor_id,
            )
        )
        corridor_group.clear()

    for i, leg in enumerate(legs):
        if leg.kind != "corridor":
            # Межэтажный переход прерывает пеший участок
            flush_group()
            if leg.to_floor_number > leg.from_floor_number:
                verb = "Поднимитесь"
            else:
                verb = "Спуститесь"
            transport = "по лестнице" if leg.kind == "stairs" else "на лифте"
            steps.append(
                StepDraft(
                    kind=leg.kind,
                    text=f"{verb} {transport} на {leg.to_floor_number} этаж",
                    distance_meters=leg.weight_meters,
                    node_ids=[leg.from_node_id, leg.to_node_id],
                    floor_id=leg.floor_id,
                )
            )
            continue

        # Коридорное ребро: проверяем стык с предыдущим коридорным ребром
        if corridor_group:
            prev = corridor_group[-1]
            junction_id = prev.to_node_id
            in_bearing = bearing_deg(prev.from_x, prev.from_y, prev.to_x, prev.to_y)
            out_bearing = bearing_deg(leg.from_x, leg.from_y, leg.to_x, leg.to_y)
            delta = signed_turn_deg(in_bearing, out_bearing)

            other_bearings = [
                b
                for eid, b in adjacency_bearings.get(junction_id, [])
                if eid not in (prev.edge_id, leg.edge_id)
            ]
            keep_side = _confusing_edge_side(out_bearing, other_bearings)
            has_confusion = keep_side is not None

            if abs(delta) < STRAIGHT_MERGE_MAX_DEG:
                if has_confusion:
                    # Почти прямо, но рядом уходит похожий проход — предупредим
                    flush_group()
                    side_word = "левее" if keep_side == "left" else "правее"
                    steps.append(
                        StepDraft(
                            kind="keep",
                            text=f"Держитесь {side_word}, не сворачивая в ответвление",
                            node_ids=[junction_id],
                            floor_id=leg.floor_id,
                        )
                    )
                # иначе — честное «прямо», участки сливаются без инструкции
            else:
                flush_group()
                kind, text = _turn_wording(delta, has_confusion)
                steps.append(
                    StepDraft(
                        kind=kind,
                        text=text,
                        node_ids=[junction_id],
                        floor_id=leg.floor_id,
                    )
                )
        corridor_group.append(leg)

    flush_group()

    # --- Финальный шаг: подход к цели от последней вершины ---
    last = legs[-1]
    exit_ppm = ppm_by_floor[last.to_floor_id]
    exit_m = euclidean_px(last.to_x, last.to_y, target_poi_x, target_poi_y) / exit_ppm
    if exit_m >= MIN_APPROACH_DIST_M:
        steps.append(
            StepDraft(
                kind="arrival",
                text=f"Пройдите {_fmt_meters(exit_m)} — вы у цели: «{target_poi_title}»",
                distance_meters=exit_m,
                node_ids=[last.to_node_id],
            )
        )
    else:
        steps.append(
            StepDraft(
                kind="arrival",
                text=f"Вы пришли: «{target_poi_title}»",
                node_ids=[last.to_node_id],
            )
        )

    return steps
