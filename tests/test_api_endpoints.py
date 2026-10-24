import uuid
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.services.s3 import s3_service

@pytest.fixture
def mock_s3():
    with patch.object(
        s3_service,
        "generate_presigned_put_url",
        AsyncMock(return_value="https://minio.test/upload?sig=mocked_signature"),
    ), patch.object(
        s3_service,
        "delete_object",
        AsyncMock(return_value=None),
    ):
        yield

@pytest.mark.asyncio
async def test_floor_plan_upload_and_confirm(client: AsyncClient, mock_s3):
    floor_id = uuid.uuid4()

    # 1. Запрос Presigned URL для 2D-плана
    resp = await client.post(
        f"/api/v1/media/floors/{floor_id}/plan/upload-url",
        json={"file_name": "blueprint.png", "content_type": "image/png"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "upload_url" in data
    assert "blueprint" in data["storage_key"] or "raw_" in data["storage_key"]

    # 2. Подтверждение загрузки
    confirm_resp = await client.post(
        f"/api/v1/media/floors/{floor_id}/plan/confirm-upload",
        json={"storage_key": data["storage_key"]},
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "processing"

@pytest.mark.asyncio
async def test_panorama_lifecycle_and_hotspots(client: AsyncClient, mock_s3):
    floor_id = uuid.uuid4()

    # 1. Создание панорамы 1 (Главный вход)
    p1_resp = await client.post(
        f"/api/v1/floors/{floor_id}/panoramas",
        json={
            "floor_id": str(floor_id),
            "title": "Главный вход",
            "x_coord": 100.5,
            "y_coord": 250.0,
            "initial_heading": 90.0,
        },
    )
    assert p1_resp.status_code == 201
    p1 = p1_resp.json()
    p1_id = p1["id"]
    assert p1["title"] == "Главный вход"
    assert p1["status"] == "pending_upload"

    # 2. Создание панорамы 2 (Конференц-зал)
    p2_resp = await client.post(
        f"/api/v1/floors/{floor_id}/panoramas",
        json={
            "floor_id": str(floor_id),
            "title": "Конференц-зал",
            "x_coord": 150.0,
            "y_coord": 280.0,
            "initial_heading": 0.0,
        },
    )
    assert p2_resp.status_code == 201
    p2_id = p2_resp.json()["id"]

    # 3. Список панорам этажа
    list_resp = await client.get(f"/api/v1/floors/{floor_id}/panoramas")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2

    # 4. Получение Presigned URL для готовой 360-фото
    url_resp = await client.post(
        f"/api/v1/panoramas/{p1_id}/upload-ready-url",
        json={"file_name": "360_shot.jpg", "content_type": "image/jpeg"},
    )
    assert url_resp.status_code == 200
    assert "upload_url" in url_resp.json()

    # 5. Создание сессии сшивки со смартфона на 8 кадров
    stitch_resp = await client.post(
        f"/api/v1/panoramas/{p1_id}/stitch-session",
        json={"frame_count": 8},
    )
    assert stitch_resp.status_code == 200
    stitch_data = stitch_resp.json()
    assert len(stitch_data["frames"]) == 8

    # 6. Создание связи (Hotspot) между панорамой 1 и 2
    hotspot_resp = await client.post(
        "/api/v1/panoramas/connections",
        json={
            "source_panorama_id": p1_id,
            "target_panorama_id": p2_id,
            "yaw": 45.0,
            "pitch": -5.0,
            "title": "Перейти в зал",
        },
    )
    assert hotspot_resp.status_code == 201
    hotspot = hotspot_resp.json()
    assert hotspot["yaw"] == 45.0

    # 7. Проверка детальной карточки с подгруженным хотспотом
    get_p1 = await client.get(f"/api/v1/panoramas/{p1_id}")
    assert get_p1.status_code == 200
    assert len(get_p1.json()["hotspots"]) == 1

    # 8. Удаление хотспота
    del_hotspot = await client.delete(f"/api/v1/panoramas/connections/{hotspot['id']}")
    assert del_hotspot.status_code == 204

    # 9. Удаление панорамы
    del_p1 = await client.delete(f"/api/v1/panoramas/{p1_id}")
    assert del_p1.status_code == 204

    # 10. Проверка 404 после удаления
    get_deleted = await client.get(f"/api/v1/panoramas/{p1_id}")
    assert get_deleted.status_code == 404
