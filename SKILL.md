---
name: indoor-spatial-map
description: "Инженерный скилл для разработки сервиса индор-навигации: шаблоны FastAPI, генерация S3 Presigned URL для MinIO, A* маршрутизация и 3D-панорамы"
---

# Инженерный скилл: Разработка сервиса «Карта пространства»

Этот скилл содержит проверенные сниппеты, архитектурные шаблоны и алгоритмы для генерации кода в проекте индор-навигации.

---

## 1. Паттерн: Асинхронный S3/MinIO клиент и Presigned URLs

Используйте `aioboto3` для неблокирующей работы с MinIO из корутин FastAPI:

```python
import aioboto3
from pydantic import BaseModel

class S3Service:
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, public_bucket: str, staging_bucket: str):
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.public_bucket = public_bucket
        self.staging_bucket = staging_bucket
        self.session = aioboto3.Session()

    def _get_client(self):
        return self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="us-east-1",
        )

    async def generate_presigned_upload_url(
        self, bucket: str, key: str, content_type: str, expires_in: int = 900
    ) -> str:
        async with self._get_client() as s3:
            url = await s3.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
            return url

    async def delete_object(self, bucket: str, key: str) -> None:
        async with self._get_client() as s3:
            await s3.delete_object(Bucket=bucket, Key=key)
```

---

## 2. Паттерн: Алгоритм индор-маршрутизации (A* Pathfinding)

Для построения маршрута между точками на 2D-плане здания используйте взвешенный граф с эвристикой евклидова расстояния:

```python
import heapq
import math
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

class PathResult(BaseModel):
    path_node_ids: List[str]
    total_distance_meters: float

def heuristic(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)

def find_shortest_path(
    start_id: str,
    target_id: str,
    nodes: Dict[str, Tuple[float, float]], # id -> (x, y)
    adjacency: Dict[str, List[Tuple[str, float, bool]]], # id -> list of (neighbor_id, weight, is_accessible)
    accessible_only: bool = False,
) -> Optional[PathResult]:
    queue = [(0.0, 0.0, start_id, [start_id])]
    visited_distances = {start_id: 0.0}

    while queue:
        estimated_total, current_dist, current_node, path = heapq.heappop(queue)

        if current_node == target_id:
            return PathResult(path_node_ids=path, total_distance_meters=current_dist)

        cx, cy = nodes[current_node]

        for neighbor_id, weight, is_accessible in adjacency.get(current_node, []):
            if accessible_only and not is_accessible:
                continue

            new_dist = current_dist + weight
            if neighbor_id not in visited_distances or new_dist < visited_distances[neighbor_id]:
                visited_distances[neighbor_id] = new_dist
                nx, ny = nodes[neighbor_id]
                h = heuristic(nx, ny, nodes[target_id][0], nodes[target_id][1])
                heapq.heappush(queue, (new_dist + h, new_dist, neighbor_id, path + [neighbor_id]))

    return None
```

---

## 3. Паттерн: Pydantic v2 Схемы ответа панорамы (Mobile Optimized)

Схема панорамы для мобильного клиента должна формировать абсолютный URL через динамический CDN префикс без хардкода хоста в базе:

```python
import uuid
from pydantic import BaseModel, ConfigDict, computed_field

class PanoramaPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    floor_id: uuid.UUID
    title: str
    x_coord: float
    y_coord: float
    initial_heading: float
    blurhash: str | None
    
    # Относительные ключи в БД
    preview_key: str | None
    original_key: str | None
    cubemap_prefix: str | None

    @computed_field
    def preview_url(self) -> str | None:
        if not self.preview_key:
            return None
        # Значение CDN префикса инжектится из настроек
        return f"/media/{self.preview_key}"

    @computed_field
    def cubemap_url_template(self) -> str | None:
        if not self.cubemap_prefix:
            return None
        return f"/media/{self.cubemap_prefix}/{{level}}/{{face}}/{{y}}_{{x}}.webp"
```

---

## 4. Паттерн: Расчет Hotspot Yaw & Pitch между двумя панорамами

Когда организатор соединяет панораму A `(x1, y1)` и панораму B `(x2, y2)`, начальный азимут для хотспота перехода можно рассчитать автоматически:

```python
import math

def calculate_initial_hotspot_angles(
    x1: float, y1: float, heading1: float,
    x2: float, y2: float
) -> tuple[float, float]:
    """
    Рассчитывает yaw и pitch для хотспота перехода из панорамы 1 в панораму 2.
    Координаты x, y на 2D-плане. heading1 - компасный азимут панорамы 1 (градусы).
    """
    dx = x2 - x1
    dy = y2 - y1
    
    # Математический угол в плоскости карты
    angle_rad = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_rad)
    
    # Смещение относительно направления взгляда панорамы
    yaw = (angle_deg - heading1 + 180) % 360 - 180
    pitch = 0.0 # по умолчанию на уровне горизонта глаз
    return round(yaw, 1), pitch
```
