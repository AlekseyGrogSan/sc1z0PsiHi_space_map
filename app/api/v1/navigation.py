import uuid
from typing import Annotated, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_space_role
from app.models.floor import Floor
from app.models.navigation import NavEdge, NavEdgeKind, NavNode, NavNodeType
from app.models.panorama import Panorama
from app.models.space import Space, SpaceMember, SpaceRole
from app.models.user import SystemRole, User
from app.repositories.floor_repository import floor_repo
from app.repositories.navigation_repository import navigation_repo
from app.repositories.space_repository import space_repo
from app.schemas.floor import FloorRead, FloorUpdate
from app.schemas.navigation import (
    NavEdgeRead,
    NavGraphRead,
    NavGraphSaveResponse,
    NavGraphUpdate,
    NavNodeRead,
    RouteRequest,
    RouteResponse,
    TransitionCreate,
    TransitionEndpointRead,
    TransitionRead,
)
from app.services.pathfinder import ELEVATOR_WEIGHT_METERS, STAIRS_WEIGHT_METERS
from app.services.routing_service import RoutingError, build_route

router = APIRouter(tags=["Navigation Graph & Routing"])


# ============================================================================
# Dependencies
# ============================================================================


async def get_floor_or_404(
    floor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Floor:
    floor = await floor_repo.get_by_id(db, floor_id)
    if not floor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Floor not found",
        )
    return floor


async def require_floor_editor(
    floor_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Floor:
    """
    Загружает этаж и проверяет, что пользователь — owner/editor
    пространства, которому этаж принадлежит (superadmin всегда допускается).
    """
    floor = await floor_repo.get_by_id(db, floor_id)
    if not floor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Floor not found",
        )
    if current_user.system_role == SystemRole.SUPERADMIN:
        return floor
    member = await space_repo.get_member(db, floor.space_id, current_user.id)
    if not member or member.role not in (SpaceRole.OWNER, SpaceRole.EDITOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Requires owner or editor role in this space",
        )
    return floor


async def _validate_node_panoramas(
    db: AsyncSession,
    floor_id: uuid.UUID,
    panorama_ids: List[uuid.UUID],
) -> None:
    """Панорама, привязываемая к вершине, должна существовать и лежать на том же этаже."""
    for panorama_id in set(panorama_ids):
        panorama = await db.get(Panorama, panorama_id)
        if not panorama:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Panorama {panorama_id} not found",
            )
        if panorama.floor_id != floor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Panorama {panorama_id} belongs to a different floor",
            )


def _transition_read(
    edge: NavEdge,
    from_node: NavNode,
    to_node: NavNode,
    from_floor: Floor,
    to_floor: Floor,
) -> TransitionRead:
    """Собирает DTO межэтажного перехода из явно переданных сущностей."""
    def endpoint(node: NavNode, floor: Floor) -> TransitionEndpointRead:
        return TransitionEndpointRead(
            node_id=node.id,
            floor_id=node.floor_id,
            floor_number=floor.floor_number,
            x=node.x,
            y=node.y,
        )

    return TransitionRead(
        id=edge.id,
        kind=edge.kind,
        weight_meters=edge.weight_meters,
        is_accessible=edge.is_accessible,
        from_endpoint=endpoint(from_node, from_floor),
        to_endpoint=endpoint(to_node, to_floor),
    )


# ============================================================================
# Граф этажа (организатор — редактирование, посетитель — чтение)
# ============================================================================


@router.get(
    "/floors/{floor_id}/navigation/graph",
    response_model=NavGraphRead,
    summary="Граф этажа: вершины и коридорные рёбра (публичный)",
)
async def get_floor_graph(
    floor: Annotated[Floor, Depends(get_floor_or_404)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NavGraphRead:
    """
    Возвращает вершины этажа и коридорные рёбра между ними.
    Межэтажные переходы (лестницы/лифты) запрашиваются отдельно —
    GET /spaces/{space_id}/navigation/transitions.
    """
    nodes = await navigation_repo.list_nodes_by_floor(db, floor.id)
    edges = await navigation_repo.list_corridor_edges_by_floor(db, floor.id)
    return NavGraphRead(
        floor_id=floor.id,
        nodes=[NavNodeRead.model_validate(n) for n in nodes],
        edges=[NavEdgeRead.model_validate(e) for e in edges],
    )


@router.put(
    "/floors/{floor_id}/navigation/graph",
    response_model=NavGraphSaveResponse,
    summary="Пакетное сохранение графа этажа (owner, editor)",
)
async def put_floor_graph(
    payload: NavGraphUpdate,
    floor: Annotated[Floor, Depends(require_floor_editor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NavGraphSaveResponse:
    """
    Полностью перезаписывает внутриэтажный граф: вершины и коридорные рёбра.

    - Каждая вершина идентифицируется клиентским ключом `ref`; для
      существующих вершин дополнительно передаётся `id`.
    - Вершины этажа, отсутствующие в запросе, удаляются. Удаление вершины,
      к которой привязан межэтажный переход, отклоняется с 409 Conflict —
      сначала удалите переход.
    - Веса рёбер вычисляются на сервере: евклидово расстояние между
      вершинами в пикселях, делённое на масштаб этажа (ppm).
    - Межэтажные переходы этим эндпоинтом не изменяются.
    """
    if not floor.ppm or floor.ppm <= 0:
        floor = await floor_repo.update(db, floor, FloorUpdate(ppm=25.0))

    # Все переданные id вершин должны принадлежать именно этому этажу
    existing_nodes = await navigation_repo.list_nodes_by_floor(db, floor.id)
    existing_ids = {n.id for n in existing_nodes}
    for node_in in payload.nodes:
        if node_in.id is not None and node_in.id not in existing_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Node {node_in.id} does not belong to this floor",
            )

    panorama_ids = [n.panorama_id for n in payload.nodes if n.panorama_id is not None]
    if panorama_ids:
        await _validate_node_panoramas(db, floor.id, panorama_ids)

    # Серверная согласованность: вершины, занятые межэтажными переходами,
    # нельзя молча удалить пакетным сохранением.
    payload_ids = {n.id for n in payload.nodes if n.id is not None}
    removed_ids = existing_ids - payload_ids
    if removed_ids:
        blocking = await navigation_repo.list_transitions_touching_nodes(
            db, list(removed_ids)
        )
        if blocking:
            blocked_node_ids = sorted(
                {
                    str(nid)
                    for e in blocking
                    for nid in (e.from_node_id, e.to_node_id)
                    if nid in removed_ids
                }
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot delete nodes referenced by inter-floor transitions. "
                    f"Remove the transitions first. Blocked node ids: {blocked_node_ids}"
                ),
            )

    nodes_payload = [
        {
            "id": n.id,
            "x": n.x,
            "y": n.y,
            "node_type": n.node_type,
            "panorama_id": n.panorama_id,
        }
        for n in payload.nodes
    ]
    ref_to_index = {n.ref: i for i, n in enumerate(payload.nodes)}
    edges_payload = [
        (ref_to_index[e.from_ref], ref_to_index[e.to_ref]) for e in payload.edges
    ]

    saved_nodes, saved_edges, index_to_id = await navigation_repo.replace_floor_graph(
        db, floor, nodes_payload, edges_payload
    )

    nodes = await navigation_repo.list_nodes_by_floor(db, floor.id)
    edges = await navigation_repo.list_corridor_edges_by_floor(db, floor.id)
    return NavGraphSaveResponse(
        floor_id=floor.id,
        node_id_map={n.ref: index_to_id[i] for i, n in enumerate(payload.nodes)},
        graph=NavGraphRead(
            floor_id=floor.id,
            nodes=[NavNodeRead.model_validate(n) for n in nodes],
            edges=[NavEdgeRead.model_validate(e) for e in edges],
        ),
    )


# ============================================================================
# Межэтажные переходы (лестницы и лифты)
# ============================================================================


@router.get(
    "/spaces/{space_id}/navigation/transitions",
    response_model=List[TransitionRead],
    summary="Список межэтажных переходов пространства (публичный)",
)
async def list_space_transitions(
    space_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[TransitionRead]:
    space = await space_repo.get_by_id(db, space_id)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        )
    edges = await navigation_repo.list_transitions_by_space(db, space_id)
    # Вершины и их этажи подгружены через selectinload в репозитории
    return [
        _transition_read(e, e.from_node, e.to_node, e.from_node.floor, e.to_node.floor)
        for e in edges
    ]


@router.post(
    "/spaces/{space_id}/navigation/transitions",
    response_model=TransitionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавление межэтажного перехода — лестницы или лифта (owner, editor)",
)
async def create_transition(
    space_id: uuid.UUID,
    payload: TransitionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        Tuple[Space, Optional[SpaceMember]],
        Depends(require_space_role([SpaceRole.OWNER, SpaceRole.EDITOR])),
    ],
) -> TransitionRead:
    """
    Создаёт межэтажное ребро между вершинами РАЗНЫХ этажей одного
    пространства. Сервер гарантирует согласованность:

    - обе вершины существуют и принадлежат этажам этого пространства;
    - этажи вершин различаются;
    - дубликат перехода между той же парой вершин отклоняется;
    - вес фиксированный: лестница = 35 м эквивалента, лифт = 30 м;
    - лестница недоступна для маломобильных, лифт — доступен;
    - типы вершин автоматически помечаются как stairs/elevator.
    """
    if payload.kind == NavEdgeKind.CORRIDOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inter-floor transition kind must be stairs or elevator",
        )
    if payload.from_node_id == payload.to_node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transition endpoints must be different nodes",
        )

    nodes = await navigation_repo.get_nodes_by_ids(
        db, [payload.from_node_id, payload.to_node_id]
    )
    nodes_by_id = {n.id: n for n in nodes}
    from_node = nodes_by_id.get(payload.from_node_id)
    to_node = nodes_by_id.get(payload.to_node_id)
    if from_node is None or to_node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both nodes not found",
        )

    # Обе вершины обязаны принадлежать этажам ЭТОГО пространства
    floors = await floor_repo.list_by_space(db, space_id)
    floors_by_id = {f.id: f for f in floors}
    from_floor = floors_by_id.get(from_node.floor_id)
    to_floor = floors_by_id.get(to_node.floor_id)
    if from_floor is None or to_floor is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both nodes must belong to floors of this space",
        )
    if from_floor.id == to_floor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inter-floor transition must connect nodes on different floors",
        )

    duplicate = await navigation_repo.find_transition_between(
        db, payload.from_node_id, payload.to_node_id
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transition between these nodes already exists",
        )

    is_stairs = payload.kind == NavEdgeKind.STAIRS
    edge = await navigation_repo.create_transition(
        db,
        from_node=from_node,
        to_node=to_node,
        kind=payload.kind,
        weight_meters=STAIRS_WEIGHT_METERS if is_stairs else ELEVATOR_WEIGHT_METERS,
        is_accessible=not is_stairs,
    )

    # Помечаем вершины типом перехода для корректной отрисовки в редакторе
    from_node.node_type = NavNodeType.STAIRS if is_stairs else NavNodeType.ELEVATOR
    to_node.node_type = from_node.node_type
    await db.flush()

    return _transition_read(edge, from_node, to_node, from_floor, to_floor)


@router.delete(
    "/spaces/{space_id}/navigation/transitions/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление межэтажного перехода (owner, editor)",
)
async def delete_transition(
    space_id: uuid.UUID,
    edge_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        Tuple[Space, Optional[SpaceMember]],
        Depends(require_space_role([SpaceRole.OWNER, SpaceRole.EDITOR])),
    ],
) -> None:
    edge = await navigation_repo.get_edge(db, edge_id)
    if not edge or edge.kind == NavEdgeKind.CORRIDOR:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transition not found",
        )
    # Переход обязан принадлежать этому пространству
    floors = await floor_repo.list_by_space(db, space_id)
    floor_ids = {f.id for f in floors}
    if (
        edge.from_node.floor_id not in floor_ids
        or edge.to_node.floor_id not in floor_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transition not found in this space",
        )
    await navigation_repo.delete_edge(db, edge)


# ============================================================================
# Маршрут (посетитель)
# ============================================================================


@router.post(
    "/spaces/{space_id}/navigation/route",
    response_model=RouteResponse,
    summary="Построение пешеходного маршрута от точки А до POI (публичный)",
)
async def calculate_route(
    space_id: uuid.UUID,
    payload: RouteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RouteResponse:
    """
    Строит оптимальный маршрут (A*) от произвольной точки «А» на этаже
    до точки интереса (POI), возможно через межэтажные переходы.

    - Точка А проецируется на ближайшее коридорное ребро этажа; маршрут
      стартует от одной из его вершин — инструкция подскажет, как дойти
      до неё.
    - Ответ содержит геометрию пути (вершины и рёбра), пошаговую
      человекопонятную инструкцию и список панорам вдоль пути.
    - `wheelchair_accessible_only=true` исключает лестницы из маршрута.
    """
    space = await space_repo.get_by_id(db, space_id)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        )
    try:
        return await build_route(db, space, payload)
    except RoutingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch(
    "/floors/{floor_id}",
    response_model=FloorRead,
    summary="Редактирование параметров этажа (масштаб ppm, название)",
)
async def update_floor_direct(
    floor_in: FloorUpdate,
    floor: Annotated[Floor, Depends(require_floor_editor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FloorRead:
    updated = await floor_repo.update(db, floor, floor_in)
    return FloorRead.model_validate(updated)
