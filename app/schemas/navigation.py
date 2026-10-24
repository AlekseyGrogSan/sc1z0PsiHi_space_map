import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.navigation import NavEdgeKind, NavNodeType

# ============================================================================
# Вершины и рёбра (чтение)
# ============================================================================


class NavNodeRead(BaseModel):
    """Вершина навигационного графа."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    floor_id: uuid.UUID
    panorama_id: Optional[uuid.UUID] = None
    x: float = Field(..., description="Координата X на 2D-плане этажа (px)")
    y: float = Field(..., description="Координата Y на 2D-плане этажа (px)")
    node_type: NavNodeType


class NavEdgeRead(BaseModel):
    """Ребро навигационного графа (вес в метрах, вычислен сервером)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    kind: NavEdgeKind
    weight_meters: float
    is_accessible: bool
    bidirectional: bool


class NavGraphRead(BaseModel):
    """
    Граф этажа для 2D-редактора и для посетителя: вершины этажа и
    коридорные рёбра между ними. Межэтажные переходы отдаются отдельно
    (GET /spaces/{space_id}/navigation/transitions).
    """

    floor_id: uuid.UUID
    nodes: List[NavNodeRead] = Field(default_factory=list)
    edges: List[NavEdgeRead] = Field(default_factory=list)


# ============================================================================
# Пакетное сохранение графа этажа (организатор)
# ============================================================================


class NavNodeInput(BaseModel):
    """
    Вершина в пакетном сохранении графа этажа.

    `ref` — произвольный строковый ключ клиента, уникальный в рамках
    запроса: на него ссылаются рёбра. Для существующей вершины дополнительно
    передаётся `id`; вершины этажа, отсутствующие в запросе, удаляются.
    """

    ref: str = Field(..., min_length=1, max_length=64, description="Временный ключ вершины в запросе")
    id: Optional[uuid.UUID] = Field(None, description="ID существующей вершины (если редактируется)")
    x: float = Field(..., description="Координата X на 2D-плане этажа (px)")
    y: float = Field(..., description="Координата Y на 2D-плане этажа (px)")
    node_type: NavNodeType = NavNodeType.WALKWAY
    panorama_id: Optional[uuid.UUID] = Field(None, description="Привязка к панораме этого же этажа")


class NavEdgeInput(BaseModel):
    """Коридорное ребро в пакетном сохранении: ссылки на ключи вершин."""

    from_ref: str = Field(..., description="Ключ (ref) начальной вершины")
    to_ref: str = Field(..., description="Ключ (ref) конечной вершины")


class NavGraphUpdate(BaseModel):
    """
    Полная перезапись внутриэтажного графа: все вершины этажа и все
    коридорные рёбра. Межэтажные переходы этим эндпоинтом не изменяются.
    """

    nodes: List[NavNodeInput] = Field(default_factory=list)
    edges: List[NavEdgeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_refs(self) -> "NavGraphUpdate":
        refs = [n.ref for n in self.nodes]
        if len(refs) != len(set(refs)):
            raise ValueError("Node refs must be unique within the request")
        node_ids = [str(n.id) for n in self.nodes if n.id is not None]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Duplicate node ids in the request")
        known = set(refs)
        seen_edges = set()
        for edge in self.edges:
            if edge.from_ref not in known or edge.to_ref not in known:
                raise ValueError(
                    f"Edge references unknown node ref: {edge.from_ref} -> {edge.to_ref}"
                )
            if edge.from_ref == edge.to_ref:
                raise ValueError("Self-loop edges are not allowed")
            pair = frozenset((edge.from_ref, edge.to_ref))
            if pair in seen_edges:
                raise ValueError(
                    f"Duplicate edge between {edge.from_ref} and {edge.to_ref}"
                )
            seen_edges.add(pair)
        return self


class NavGraphSaveResponse(BaseModel):
    """Результат пакетного сохранения: соответствие ключей и ID + граф."""

    floor_id: uuid.UUID
    node_id_map: Dict[str, uuid.UUID] = Field(
        ..., description="Соответствие клиентских ключей (ref) реальным ID вершин"
    )
    graph: NavGraphRead


# ============================================================================
# Межэтажные переходы (лестницы и лифты)
# ============================================================================


class TransitionCreate(BaseModel):
    """Создание межэтажного перехода между вершинами разных этажей."""

    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    kind: NavEdgeKind = Field(
        ..., description="Тип перехода: stairs (лестница) или elevator (лифт)"
    )


class TransitionEndpointRead(BaseModel):
    """Краткая информация о вершине перехода и её этаже."""

    node_id: uuid.UUID
    floor_id: uuid.UUID
    floor_number: int
    x: float
    y: float


class TransitionRead(BaseModel):
    """Межэтажное ребро с информацией о концах (для редактора и посетителя)."""

    id: uuid.UUID
    kind: NavEdgeKind
    weight_meters: float
    is_accessible: bool
    from_endpoint: TransitionEndpointRead
    to_endpoint: TransitionEndpointRead


# ============================================================================
# Маршрут (посетитель)
# ============================================================================


class RouteRequest(BaseModel):
    """
    Запрос пешеходного маршрута: от произвольной точки «А» на этаже
    (не обязана совпадать с вершиной графа) до точки интереса (POI).
    """

    floor_id: uuid.UUID = Field(..., description="Этаж, на котором находится пользователь")
    x: float = Field(..., description="Координата X точки А на плане этажа (px)")
    y: float = Field(..., description="Координата Y точки А на плане этажа (px)")
    to_poi_id: uuid.UUID = Field(..., description="ID точки интереса — цели маршрута")
    wheelchair_accessible_only: bool = Field(
        False, description="Строить маршрут без лестниц (только доступные рёбра)"
    )


class RoutePointRead(BaseModel):
    """Точка на плане этажа."""

    x: float
    y: float
    floor_id: uuid.UUID


class RouteEndpointInfo(BaseModel):
    """
    Информация о входе/выходе с графа: куда спроецирована точка и к какой
    вершине маршрута нужно дойти пешком.
    """

    point: RoutePointRead = Field(..., description="Исходная точка (А или POI)")
    projected_point: Optional[RoutePointRead] = Field(
        None, description="Проекция точки на ближайшее ребро графа"
    )
    node_id: Optional[uuid.UUID] = Field(
        None, description="Вершина маршрута, к которой нужно дойти"
    )
    walk_distance_meters: float = Field(
        0.0, description="Пешая дистанция от точки до вершины маршрута (м)"
    )


class RoutePathNodeRead(BaseModel):
    """Вершина на пути (с номером этажа для группировки отрисовки)."""

    id: uuid.UUID
    floor_id: uuid.UUID
    floor_number: int
    x: float
    y: float
    node_type: NavNodeType


class RoutePathEdgeRead(BaseModel):
    """Ребро на пути в порядке прохождения."""

    id: uuid.UUID
    kind: NavEdgeKind
    from_node_id: uuid.UUID
    to_node_id: uuid.UUID
    weight_meters: float


class RouteStepRead(BaseModel):
    """Один шаг человекопонятной инструкции."""

    kind: str = Field(
        ...,
        description="Тип шага: approach | walk | keep | turn | stairs | elevator | arrival",
    )
    text: str = Field(..., description="Текст подсказки для пользователя")
    distance_meters: Optional[float] = Field(
        None, description="Длина участка в метрах (для шагов движения)"
    )
    floor_id: Optional[uuid.UUID] = None
    node_ids: List[uuid.UUID] = Field(
        default_factory=list, description="Вершины пути, относящиеся к шагу"
    )


class RouteResponse(BaseModel):
    """Рассчитанный маршрут: геометрия пути + пошаговая инструкция."""

    total_distance_meters: float
    estimated_time_seconds: int
    entry: RouteEndpointInfo = Field(..., description="Вход на граф из точки А")
    exit: RouteEndpointInfo = Field(..., description="Сход с графа к целевой POI")
    nodes: List[RoutePathNodeRead] = Field(
        default_factory=list, description="Вершины пути в порядке прохождения"
    )
    edges: List[RoutePathEdgeRead] = Field(
        default_factory=list, description="Рёбра пути в порядке прохождения"
    )
    steps: List[RouteStepRead] = Field(default_factory=list)
    panorama_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="ID панорам вдоль маршрута (в порядке пути) для виртуального прохода",
    )
