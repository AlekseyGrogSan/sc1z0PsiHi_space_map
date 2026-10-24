import uuid
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.floor import Floor
from app.models.navigation import NavEdge, NavEdgeKind, NavNode
from app.services.pathfinder import corridor_weight_meters


class NavigationRepository:
    """Доступ к вершинам и рёбрам навигационного графа."""

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------

    async def get_node(
        self, db: AsyncSession, node_id: uuid.UUID
    ) -> Optional[NavNode]:
        stmt = select(NavNode).where(NavNode.id == node_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_nodes_by_ids(
        self, db: AsyncSession, node_ids: Sequence[uuid.UUID]
    ) -> List[NavNode]:
        if not node_ids:
            return []
        stmt = select(NavNode).where(NavNode.id.in_(node_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_nodes_by_floor(
        self, db: AsyncSession, floor_id: uuid.UUID
    ) -> List[NavNode]:
        stmt = (
            select(NavNode)
            .where(NavNode.floor_id == floor_id)
            .order_by(NavNode.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_corridor_edges_by_floor(
        self, db: AsyncSession, floor_id: uuid.UUID
    ) -> List[NavEdge]:
        """Коридорные рёбра, обе вершины которых лежат на заданном этаже."""
        from_node = NavNode.__table__.alias("from_node")
        to_node = NavNode.__table__.alias("to_node")
        stmt = (
            select(NavEdge)
            .join(from_node, NavEdge.from_node_id == from_node.c.id)
            .join(to_node, NavEdge.to_node_id == to_node.c.id)
            .where(
                from_node.c.floor_id == floor_id,
                to_node.c.floor_id == floor_id,
                NavEdge.kind == NavEdgeKind.CORRIDOR,
            )
            .order_by(NavEdge.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_transitions_by_space(
        self, db: AsyncSession, space_id: uuid.UUID
    ) -> List[NavEdge]:
        """
        Межэтажные рёбра (лестницы/лифты) пространства — с подгруженными
        вершинами и их этажами для ответа API.
        """
        from_node = NavNode.__table__.alias("from_node")
        to_node = NavNode.__table__.alias("to_node")
        from_floor = Floor.__table__.alias("from_floor")
        to_floor = Floor.__table__.alias("to_floor")
        stmt = (
            select(NavEdge)
            .join(from_node, NavEdge.from_node_id == from_node.c.id)
            .join(to_node, NavEdge.to_node_id == to_node.c.id)
            .join(from_floor, from_node.c.floor_id == from_floor.c.id)
            .join(to_floor, to_node.c.floor_id == to_floor.c.id)
            .where(
                from_floor.c.space_id == space_id,
                to_floor.c.space_id == space_id,
                NavEdge.kind != NavEdgeKind.CORRIDOR,
            )
            .options(
                selectinload(NavEdge.from_node).selectinload(NavNode.floor),
                selectinload(NavEdge.to_node).selectinload(NavNode.floor),
            )
            .order_by(NavEdge.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_space_graph(
        self, db: AsyncSession, space_id: uuid.UUID
    ) -> Tuple[List[Floor], List[NavNode], List[NavEdge]]:
        """
        Полный граф пространства для маршрутизации: все этажи, все вершины
        этих этажей и все рёбра (и коридорные, и межэтажные) между ними.
        """
        floors = list(
            (
                await db.execute(
                    select(Floor).where(Floor.space_id == space_id)
                )
            )
            .scalars()
            .all()
        )
        floor_ids = [f.id for f in floors]
        if not floor_ids:
            return floors, [], []

        nodes = list(
            (
                await db.execute(
                    select(NavNode).where(NavNode.floor_id.in_(floor_ids))
                )
            )
            .scalars()
            .all()
        )
        node_ids = [n.id for n in nodes]
        if not node_ids:
            return floors, nodes, []

        edges = list(
            (
                await db.execute(
                    select(NavEdge).where(
                        NavEdge.from_node_id.in_(node_ids),
                        NavEdge.to_node_id.in_(node_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        return floors, nodes, edges

    async def get_edge(
        self, db: AsyncSession, edge_id: uuid.UUID
    ) -> Optional[NavEdge]:
        stmt = (
            select(NavEdge)
            .where(NavEdge.id == edge_id)
            .options(
                selectinload(NavEdge.from_node),
                selectinload(NavEdge.to_node),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_transition_between(
        self, db: AsyncSession, node_a_id: uuid.UUID, node_b_id: uuid.UUID
    ) -> Optional[NavEdge]:
        """Существующий межэтажный переход между парой вершин (в любую сторону)."""
        stmt = select(NavEdge).where(
            NavEdge.kind != NavEdgeKind.CORRIDOR,
            (
                ((NavEdge.from_node_id == node_a_id) & (NavEdge.to_node_id == node_b_id))
                | ((NavEdge.from_node_id == node_b_id) & (NavEdge.to_node_id == node_a_id))
            ),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_transitions_touching_nodes(
        self, db: AsyncSession, node_ids: Sequence[uuid.UUID]
    ) -> List[NavEdge]:
        """Межэтажные рёбра, инцидентные любой из указанных вершин."""
        if not node_ids:
            return []
        stmt = select(NavEdge).where(
            NavEdge.kind != NavEdgeKind.CORRIDOR,
            (NavEdge.from_node_id.in_(node_ids)) | (NavEdge.to_node_id.in_(node_ids)),
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Запись
    # ------------------------------------------------------------------

    async def replace_floor_graph(
        self,
        db: AsyncSession,
        floor: Floor,
        nodes_payload: List[Dict],
        edges_payload: List[Tuple[int, int]],
    ) -> Tuple[List[NavNode], List[NavEdge], Dict[int, uuid.UUID]]:
        """
        Полная перезапись внутриэтажного графа.

        :param nodes_payload: список словарей с полями вершины
            (id — опционально, x, y, node_type, panorama_id).
        :param edges_payload: список пар (from_index, to_index) — индексы
            вершин в nodes_payload.
        :return: (вершины, рёбра, {индекс_в_payload: id_вершины}).

        Важно: межэтажные рёбра здесь не трогаем — их согласованность
        (запрет удаления занятых вершин) проверяется слоем выше.
        """
        existing_nodes = await self.list_nodes_by_floor(db, floor.id)
        existing_by_id = {n.id: n for n in existing_nodes}

        payload_ids = {p.get("id") for p in nodes_payload if p.get("id") is not None}
        removed_node_ids = [nid for nid in existing_by_id if nid not in payload_ids]

        # 1. Удаляем все коридорные рёбра этажа (они пересоздадутся ниже)
        corridor_edges = await self.list_corridor_edges_by_floor(db, floor.id)
        for edge in corridor_edges:
            await db.delete(edge)
        await db.flush()

        # 2. Удаляем вершины, отсутствующие в payload
        for node_id in removed_node_ids:
            await db.delete(existing_by_id[node_id])
        await db.flush()

        # 3. Upsert вершин
        saved_nodes: List[NavNode] = []
        index_to_id: Dict[int, uuid.UUID] = {}
        for idx, payload in enumerate(nodes_payload):
            node_id = payload.get("id")
            if node_id is not None and node_id in existing_by_id:
                node = existing_by_id[node_id]
                node.x = payload["x"]
                node.y = payload["y"]
                node.node_type = payload["node_type"]
                node.panorama_id = payload.get("panorama_id")
            else:
                node = NavNode(
                    floor_id=floor.id,
                    x=payload["x"],
                    y=payload["y"],
                    node_type=payload["node_type"],
                    panorama_id=payload.get("panorama_id"),
                )
                db.add(node)
            saved_nodes.append(node)
        await db.flush()
        for idx, node in enumerate(saved_nodes):
            index_to_id[idx] = node.id

        # 4. Создаём коридорные рёбра с серверным расчётом веса
        saved_edges: List[NavEdge] = []
        for from_idx, to_idx in edges_payload:
            a, b = saved_nodes[from_idx], saved_nodes[to_idx]
            edge = NavEdge(
                from_node_id=a.id,
                to_node_id=b.id,
                kind=NavEdgeKind.CORRIDOR,
                weight_meters=corridor_weight_meters(a.x, a.y, b.x, b.y, floor.ppm),
                is_accessible=True,
                bidirectional=True,
            )
            db.add(edge)
            saved_edges.append(edge)
        await db.flush()

        return saved_nodes, saved_edges, index_to_id

    async def create_transition(
        self,
        db: AsyncSession,
        from_node: NavNode,
        to_node: NavNode,
        kind: NavEdgeKind,
        weight_meters: float,
        is_accessible: bool,
    ) -> NavEdge:
        edge = NavEdge(
            from_node_id=from_node.id,
            to_node_id=to_node.id,
            kind=kind,
            weight_meters=weight_meters,
            is_accessible=is_accessible,
            bidirectional=True,
        )
        db.add(edge)
        await db.flush()
        await db.refresh(edge)
        return edge

    async def delete_edge(self, db: AsyncSession, edge: NavEdge) -> None:
        await db.delete(edge)
        await db.flush()


navigation_repo = NavigationRepository()
