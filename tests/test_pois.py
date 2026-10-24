import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.floor import Floor
from app.models.panorama import Panorama
from app.models.space import Space


@pytest.fixture
async def floor(db_session: AsyncSession) -> Floor:
    space = Space(title="Экспоцентр", slug=f"expo-{uuid.uuid4().hex[:8]}")
    db_session.add(space)
    await db_session.flush()
    floor = Floor(space_id=space.id, floor_number=1, title="1 этаж")
    db_session.add(floor)
    await db_session.commit()
    return floor


@pytest.fixture
async def other_floor(db_session: AsyncSession, floor: Floor) -> Floor:
    floor2 = Floor(space_id=floor.space_id, floor_number=2, title="2 этаж")
    db_session.add(floor2)
    await db_session.commit()
    return floor2


@pytest.fixture
async def panorama(db_session: AsyncSession, floor: Floor) -> Panorama:
    pano = Panorama(
        floor_id=floor.id,
        title="Главный холл",
        x_coord=100.0,
        y_coord=200.0,
        initial_heading=0.0,
        status="ready",
    )
    db_session.add(pano)
    await db_session.commit()
    return pano


def poi_payload(**overrides) -> dict:
    payload = {
        "title": "Стенд ТТК",
        "category": "stand",
        "description": "Демонстрация решений индор-навигации",
        "x_coord": 380.0,
        "y_coord": 710.0,
    }
    payload.update(overrides)
    return payload


# ============================================================================
# CRUD
# ============================================================================

@pytest.mark.asyncio
async def test_poi_crud_lifecycle(client: AsyncClient, floor: Floor):
    # 1. Создание
    create_resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(),
    )
    assert create_resp.status_code == 201
    poi = create_resp.json()
    poi_id = poi["id"]
    assert poi["floor_id"] == str(floor.id)
    assert poi["title"] == "Стенд ТТК"
    assert poi["category"] == "stand"
    assert poi["x_coord"] == 380.0
    assert poi["panorama_id"] is None
    assert poi["yaw_in_panorama"] is None

    # 2. Получение по id
    get_resp = await client.get(f"/api/v1/pois/{poi_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == poi_id

    # 3. Список POI этажа
    list_resp = await client.get(f"/api/v1/floors/{floor.id}/pois")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 4. Редактирование
    patch_resp = await client.patch(
        f"/api/v1/pois/{poi_id}",
        json={"title": "Стойка регистрации", "category": "info", "x_coord": 400.5},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["title"] == "Стойка регистрации"
    assert updated["category"] == "info"
    assert updated["x_coord"] == 400.5
    assert updated["y_coord"] == 710.0  # не изменилось

    # 5. Удаление
    del_resp = await client.delete(f"/api/v1/pois/{poi_id}")
    assert del_resp.status_code == 204

    # 6. 404 после удаления
    get_deleted = await client.get(f"/api/v1/pois/{poi_id}")
    assert get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_list_pois_only_for_own_floor(
    client: AsyncClient, floor: Floor, other_floor: Floor
):
    await client.post(f"/api/v1/floors/{floor.id}/pois", json=poi_payload(title="WC"))
    await client.post(f"/api/v1/floors/{floor.id}/pois", json=poi_payload(title="Wi-Fi"))
    await client.post(f"/api/v1/floors/{other_floor.id}/pois", json=poi_payload(title="Кафе"))

    list_resp = await client.get(f"/api/v1/floors/{floor.id}/pois")
    assert list_resp.status_code == 200
    titles = {p["title"] for p in list_resp.json()}
    assert titles == {"WC", "Wi-Fi"}


@pytest.mark.asyncio
async def test_poi_not_found_errors(client: AsyncClient, floor: Floor):
    missing_id = uuid.uuid4()
    assert (await client.get(f"/api/v1/pois/{missing_id}")).status_code == 404
    assert (await client.patch(f"/api/v1/pois/{missing_id}", json={"title": "X"})).status_code == 404
    assert (await client.delete(f"/api/v1/pois/{missing_id}")).status_code == 404
    # Создание на несуществующем этаже
    resp = await client.post(f"/api/v1/floors/{uuid.uuid4()}/pois", json=poi_payload())
    assert resp.status_code == 404


# ============================================================================
# Привязка к панораме
# ============================================================================

@pytest.mark.asyncio
async def test_create_poi_with_panorama_binding(
    client: AsyncClient, floor: Floor, panorama: Panorama
):
    resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(
            panorama_id=str(panorama.id),
            yaw_in_panorama=45.2,
            pitch_in_panorama=12.0,
        ),
    )
    assert resp.status_code == 201
    poi = resp.json()
    assert poi["panorama_id"] == str(panorama.id)
    assert poi["yaw_in_panorama"] == 45.2
    assert poi["pitch_in_panorama"] == 12.0


@pytest.mark.asyncio
async def test_bind_and_unbind_panorama_via_patch(
    client: AsyncClient, floor: Floor, panorama: Panorama
):
    create_resp = await client.post(f"/api/v1/floors/{floor.id}/pois", json=poi_payload())
    poi_id = create_resp.json()["id"]

    # Привязка к существующей панораме с углами
    bind_resp = await client.patch(
        f"/api/v1/pois/{poi_id}",
        json={
            "panorama_id": str(panorama.id),
            "yaw_in_panorama": -30.0,
            "pitch_in_panorama": 5.0,
        },
    )
    assert bind_resp.status_code == 200
    bound = bind_resp.json()
    assert bound["panorama_id"] == str(panorama.id)
    assert bound["yaw_in_panorama"] == -30.0

    # Отвязка: panorama_id=null сбрасывает и углы
    unbind_resp = await client.patch(
        f"/api/v1/pois/{poi_id}",
        json={"panorama_id": None},
    )
    assert unbind_resp.status_code == 200
    unbound = unbind_resp.json()
    assert unbound["panorama_id"] is None
    assert unbound["yaw_in_panorama"] is None
    assert unbound["pitch_in_panorama"] is None


@pytest.mark.asyncio
async def test_bind_to_missing_panorama_returns_404(client: AsyncClient, floor: Floor):
    resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(panorama_id=str(uuid.uuid4())),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bind_to_panorama_of_other_floor_returns_400(
    client: AsyncClient, floor: Floor, other_floor: Floor, db_session: AsyncSession
):
    other_pano = Panorama(
        floor_id=other_floor.id, title="Лифт", x_coord=0.0, y_coord=0.0, status="ready"
    )
    db_session.add(other_pano)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(panorama_id=str(other_pano.id), yaw_in_panorama=10.0),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_angles_without_bound_panorama_returns_400(
    client: AsyncClient, floor: Floor
):
    create_resp = await client.post(f"/api/v1/floors/{floor.id}/pois", json=poi_payload())
    poi_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/pois/{poi_id}",
        json={"yaw_in_panorama": 15.0},
    )
    assert resp.status_code == 400


# ============================================================================
# Валидация входных данных
# ============================================================================

@pytest.mark.asyncio
async def test_create_poi_validation_errors(client: AsyncClient, floor: Floor):
    # Неизвестная категория
    resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(category="parking"),
    )
    assert resp.status_code == 422

    # Углы без panorama_id
    resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(yaw_in_panorama=10.0),
    )
    assert resp.status_code == 422

    # yaw вне диапазона (-180..180)
    resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(panorama_id=str(uuid.uuid4()), yaw_in_panorama=270.0),
    )
    assert resp.status_code == 422

    # Пустое название
    resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(title=""),
    )
    assert resp.status_code == 422

    # Все допустимые категории принимаются
    for category in ("stand", "wifi", "wc", "info", "food"):
        resp = await client.post(
            f"/api/v1/floors/{floor.id}/pois",
            json=poi_payload(category=category),
        )
        assert resp.status_code == 201, category


# ============================================================================
# POI Photo Gallery
# ============================================================================


@pytest.mark.asyncio
async def test_poi_photo_upload_url_and_confirm(
    client: AsyncClient, floor: Floor
):
    """Получение presigned URL → подтверждение загрузки → появление фото в списке."""
    # Создаём POI
    create_resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(title="Стенд с фотографиями"),
    )
    assert create_resp.status_code == 201
    poi_id = create_resp.json()["id"]

    # 1. Получаем presigned URL для загрузки
    upload_resp = await client.post(
        f"/api/v1/pois/{poi_id}/photos/upload-url",
        json={"file_name": "photo.jpg", "content_type": "image/jpeg"},
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert "upload_url" in upload_data
    assert "storage_key" in upload_data
    assert upload_data["expires_in_seconds"] == 900
    storage_key_1 = upload_data["storage_key"]
    assert "poi_photos/" in storage_key_1

    # 2. Подтверждаем загрузку
    confirm_resp = await client.post(
        f"/api/v1/pois/{poi_id}/photos/confirm-upload",
        json={"storage_key": storage_key_1},
    )
    assert confirm_resp.status_code == 201
    photo = confirm_resp.json()
    assert photo["poi_id"] == poi_id
    assert photo["storage_key"] == storage_key_1
    assert photo["sort_order"] == 0  # первое фото
    assert "url" in photo  # computed_field: полный URL

    # 3. Получаем второе presigned URL и подтверждаем
    upload_resp2 = await client.post(
        f"/api/v1/pois/{poi_id}/photos/upload-url",
        json={"file_name": "photo2.webp", "content_type": "image/webp"},
    )
    assert upload_resp2.status_code == 200
    storage_key_2 = upload_resp2.json()["storage_key"]

    confirm_resp2 = await client.post(
        f"/api/v1/pois/{poi_id}/photos/confirm-upload",
        json={"storage_key": storage_key_2},
    )
    assert confirm_resp2.status_code == 201
    assert confirm_resp2.json()["sort_order"] == 1  # второе фото

    # 4. Список фотографий POI
    list_resp = await client.get(f"/api/v1/pois/{poi_id}/photos")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["poi_id"] == poi_id
    assert len(list_data["photos"]) == 2
    # Проверяем порядок
    assert list_data["photos"][0]["sort_order"] == 0
    assert list_data["photos"][1]["sort_order"] == 1


@pytest.mark.asyncio
async def test_poi_photo_reorder(
    client: AsyncClient, floor: Floor
):
    """Изменение порядка фотографий в галерее."""
    create_resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(),
    )
    poi_id = create_resp.json()["id"]

    # Создаём 3 фотографии
    photo_ids = []
    for _ in range(3):
        upload_resp = await client.post(
            f"/api/v1/pois/{poi_id}/photos/upload-url",
            json={"file_name": "p.jpg", "content_type": "image/jpeg"},
        )
        sk = upload_resp.json()["storage_key"]
        conf = await client.post(
            f"/api/v1/pois/{poi_id}/photos/confirm-upload",
            json={"storage_key": sk},
        )
        photo_ids.append(conf.json()["id"])

    # Меняем порядок: [2, 0, 1]
    new_order = [photo_ids[2], photo_ids[0], photo_ids[1]]
    reorder_resp = await client.patch(
        f"/api/v1/pois/{poi_id}/photos/reorder",
        json={"photo_ids": new_order},
    )
    assert reorder_resp.status_code == 200
    reordered = reorder_resp.json()["photos"]
    assert reordered[0]["id"] == photo_ids[2]
    assert reordered[1]["id"] == photo_ids[0]
    assert reordered[2]["id"] == photo_ids[1]

    # Проверяем через GET
    list_resp = await client.get(f"/api/v1/pois/{poi_id}/photos")
    listed = list_resp.json()["photos"]
    assert listed[0]["id"] == photo_ids[2]
    assert listed[1]["id"] == photo_ids[0]
    assert listed[2]["id"] == photo_ids[1]


@pytest.mark.asyncio
async def test_poi_photo_delete(
    client: AsyncClient, floor: Floor
):
    """Удаление фотографии из галереи."""
    create_resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(),
    )
    poi_id = create_resp.json()["id"]

    # Создаём фото
    upload_resp = await client.post(
        f"/api/v1/pois/{poi_id}/photos/upload-url",
        json={"file_name": "p.jpg", "content_type": "image/jpeg"},
    )
    storage_key = upload_resp.json()["storage_key"]
    confirm_resp = await client.post(
        f"/api/v1/pois/{poi_id}/photos/confirm-upload",
        json={"storage_key": storage_key},
    )
    photo_id = confirm_resp.json()["id"]

    # Удаляем
    delete_resp = await client.delete(
        f"/api/v1/pois/{poi_id}/photos/{photo_id}",
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    # Список пуст
    list_resp = await client.get(f"/api/v1/pois/{poi_id}/photos")
    assert len(list_resp.json()["photos"]) == 0

    # Повторное удаление — 404
    delete_again = await client.delete(
        f"/api/v1/pois/{poi_id}/photos/{photo_id}",
    )
    assert delete_again.status_code == 404


@pytest.mark.asyncio
async def test_poi_photo_errors(
    client: AsyncClient, floor: Floor
):
    """Проверка ошибок при работе с фотографиями."""
    missing_poi_id = str(uuid.uuid4())

    # upload-url на несуществующий POI
    resp = await client.post(
        f"/api/v1/pois/{missing_poi_id}/photos/upload-url",
        json={"file_name": "p.jpg", "content_type": "image/jpeg"},
    )
    assert resp.status_code == 404

    # confirm-upload на несуществующий POI
    resp = await client.post(
        f"/api/v1/pois/{missing_poi_id}/photos/confirm-upload",
        json={"storage_key": "poi_photos/x/y.jpg"},
    )
    assert resp.status_code == 404

    # Создаём POI и проверяем delete несуществующего фото
    create_resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(),
    )
    poi_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/pois/{poi_id}/photos/{uuid.uuid4()}",
    )
    assert resp.status_code == 404

    # reorder с неверными ID
    resp = await client.patch(
        f"/api/v1/pois/{poi_id}/photos/reorder",
        json={"photo_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_public_poi_photos_endpoint(
    client: AsyncClient, floor: Floor
):
    """Публичный эндпоинт получения фотографий POI."""
    create_resp = await client.post(
        f"/api/v1/floors/{floor.id}/pois",
        json=poi_payload(title="Витрина"),
    )
    poi_id = create_resp.json()["id"]

    # Добавляем 2 фото
    for _ in range(2):
        up = await client.post(
            f"/api/v1/pois/{poi_id}/photos/upload-url",
            json={"file_name": "p.jpg", "content_type": "image/jpeg"},
        )
        await client.post(
            f"/api/v1/pois/{poi_id}/photos/confirm-upload",
            json={"storage_key": up.json()["storage_key"]},
        )

    # Публичный эндпоинт
    resp = await client.get(f"/api/v1/public/pois/{poi_id}/photos")
    assert resp.status_code == 200
    data = resp.json()
    assert data["poi_id"] == poi_id
    assert data["poi_title"] == "Витрина"
    assert len(data["photos"]) == 2
    for photo in data["photos"]:
        assert "url" in photo
        assert "/spaces-public/poi_photos/" in photo["url"]

    # Несуществующий POI — 404
    resp = await client.get(f"/api/v1/public/pois/{uuid.uuid4()}/photos")
    assert resp.status_code == 404
