import io
import uuid
import pytest
from httpx import AsyncClient
from PIL import Image
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
    ), patch.object(
        s3_service,
        "put_bytes",
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
async def test_direct_floor_plan_upload_png_and_pdf(client: AsyncClient, organizer_user, auth_headers, mock_s3):
    # 1. Создаем тестовое пространство
    space_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Экспохолл", "slug": "expo-hall"},
    )
    assert space_resp.status_code == 201
    space_id = space_resp.json()["id"]

    # 2. Создаем этаж
    floor_resp = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={"floor_number": 1, "title": "1 этаж"},
    )
    assert floor_resp.status_code == 201
    floor_id = floor_resp.json()["id"]

    # 3. Загружаем PNG-план с масштабом PPM
    png_buf = io.BytesIO()
    Image.new("RGB", (800, 600), color="white").save(png_buf, format="PNG")
    png_bytes = png_buf.getvalue()

    upload_png_resp = await client.post(
        f"/api/v1/media/floors/{floor_id}/plan/upload?ppm=25.0",
        files={"file": ("floor1.png", png_bytes, "image/png")},
    )
    assert upload_png_resp.status_code == 200
    png_data = upload_png_resp.json()
    assert png_data["width_px"] == 800
    assert png_data["height_px"] == 600
    assert png_data["ppm"] == 25.0
    assert "optimized.webp" in png_data["plan_url"]

    # 4. Загружаем PDF-план
    pdf_buf = io.BytesIO()
    Image.new("RGB", (1000, 750), color="blue").save(pdf_buf, format="PDF")
    pdf_bytes = pdf_buf.getvalue()

    upload_pdf_resp = await client.post(
        f"/api/v1/media/floors/{floor_id}/plan/upload",
        files={"file": ("blueprint.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_pdf_resp.status_code == 200
    pdf_data = upload_pdf_resp.json()
    assert pdf_data["width_px"] > 0
    assert pdf_data["height_px"] > 0
    assert "optimized.webp" in pdf_data["plan_url"]

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


@pytest.mark.asyncio
async def test_direct_floor_panorama_upload(client: AsyncClient, organizer_user, auth_headers, mock_s3):
    """
    Проверяет прямой multipart-upload готовой 360-панорамы:
    - генерация превью, blurhash и кубических граней
    - сохранение в хранилище и статус ready
    - автоматическое создание связанной точки POI с panorama_id
    """
    # 1. Пространство и этаж
    space_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Музей 360", "slug": "museum-360"},
    )
    space_id = space_resp.json()["id"]

    floor_resp = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={"floor_number": 1, "title": "Основной зал", "ppm": 20.0},
    )
    floor_id = floor_resp.json()["id"]

    # 2. Создаем тестовое эквидистантное изображение 512x256
    img = Image.new("RGB", (512, 256), color=(70, 130, 180))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    # 3. Загружаем через прямой multipart endpoint
    upload_resp = await client.post(
        f"/api/v1/floors/{floor_id}/panoramas/upload",
        headers=auth_headers,
        data={
            "title": "Панорама центрального зала",
            "x_coord": 350.0,
            "y_coord": 220.0,
            "initial_heading": 45.0,
        },
        files={
            "file": ("hall_360.jpg", buf.getvalue(), "image/jpeg"),
        },
    )
    assert upload_resp.status_code == 201, f"Ошибка загрузки: {upload_resp.text}"
    pano_data = upload_resp.json()
    assert pano_data["status"] == "ready"
    assert pano_data["title"] == "Панорама центрального зала"
    assert pano_data["x_coord"] == 350.0
    assert pano_data["y_coord"] == 220.0
    assert pano_data["preview_key"] is not None
    assert pano_data["original_key"] is not None
    assert pano_data["cubemap_prefix"] is not None

    # 4. Проверяем, что создалась привязанная POI на этаже
    pois_resp = await client.get(f"/api/v1/floors/{floor_id}/pois", headers=auth_headers)
    assert pois_resp.status_code == 200
    floor_pois = pois_resp.json()
    assert len(floor_pois) == 1
    poi = floor_pois[0]
    assert poi["title"] == "Панорама центрального зала"
    assert poi["panorama_id"] == pano_data["id"]
    assert poi["x_coord"] == 350.0
    assert poi["y_coord"] == 220.0
