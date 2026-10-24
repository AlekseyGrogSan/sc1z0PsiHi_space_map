import enum
import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.floor import Floor


class NavNodeType(str, enum.Enum):
    """Тип вершины навигационного графа (влияет на отрисовку в редакторе)."""

    WALKWAY = "walkway"    # обычная точка коридора / открытого зала
    DOOR = "door"          # дверной проём
    STAIRS = "stairs"      # лестничная площадка
    ELEVATOR = "elevator"  # холл лифта


class NavEdgeKind(str, enum.Enum):
    """
    Тип ребра навигационного графа.

    Разделение важно для редактора (разная отрисовка) и для серверной
    согласованности: межэтажные рёбра (stairs/elevator) создаются отдельным
    эндпоинтом и не могут быть изменены пакетным сохранением графа этажа.
    """

    CORRIDOR = "corridor"  # пешеходный переход в пределах одного этажа
    STAIRS = "stairs"      # межэтажный переход по лестнице
    ELEVATOR = "elevator"  # межэтажный переход на лифте


class NavNode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Вершина навигационного графа на 2D-плане этажа.

    Координаты (x, y) — в пикселях чертежа этажа; масштаб задаёт floor.ppm
    (pixels per meter), по нему сервер вычисляет веса рёбер в метрах.
    """

    __tablename__ = "nav_nodes"

    floor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("floors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Опциональная привязка к панораме: вершина совпадает с точкой съёмки,
    # что позволяет отдать посетителю панорамы вдоль маршрута.
    panorama_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("panoramas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    node_type: Mapped[NavNodeType] = mapped_column(
        Enum(
            NavNodeType,
            name="nav_node_type_enum",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=NavNodeType.WALKWAY,
    )

    floor: Mapped["Floor"] = relationship("Floor", back_populates="nav_nodes")

    # ORM-каскады: удаление вершины удаляет все инцидентные рёбра
    # (в т.ч. в SQLite-тестах, где FK-каскады БД по умолчанию выключены).
    outgoing_edges: Mapped[List["NavEdge"]] = relationship(
        "NavEdge",
        foreign_keys="NavEdge.from_node_id",
        back_populates="from_node",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[List["NavEdge"]] = relationship(
        "NavEdge",
        foreign_keys="NavEdge.to_node_id",
        back_populates="to_node",
        cascade="all, delete-orphan",
    )


class NavEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Ребро навигационного графа.

    Коридорные рёбра (kind=corridor) связывают вершины одного этажа, их вес
    вычисляется сервером как евклидово расстояние между вершинами, делённое
    на ppm этажа. Межэтажные рёбра (stairs/elevator) связывают вершины разных
    этажей одного пространства и имеют фиксированный эквивалентный вес
    (лестница = 35 м пути по прямой).

    Рёбра по умолчанию двунаправленные (bidirectional=True).
    """

    __tablename__ = "nav_edges"

    from_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("nav_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("nav_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[NavEdgeKind] = mapped_column(
        Enum(
            NavEdgeKind,
            name="nav_edge_kind_enum",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=NavEdgeKind.CORRIDOR,
        index=True,
    )
    weight_meters: Mapped[float] = mapped_column(Float, nullable=False)
    # Доступность для маломобильных посетителей (лестницы = False).
    is_accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Двунаправленность: False зарезервировано под односторонние проходы.
    bidirectional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    from_node: Mapped["NavNode"] = relationship(
        "NavNode", foreign_keys=[from_node_id], back_populates="outgoing_edges"
    )
    to_node: Mapped["NavNode"] = relationship(
        "NavNode", foreign_keys=[to_node_id], back_populates="incoming_edges"
    )
