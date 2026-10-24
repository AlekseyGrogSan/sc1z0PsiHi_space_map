import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_public_space_not_found_when_unpublished(client: AsyncClient, auth_headers: dict):
    # 1. Create space (default is_published=False)
    create_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Секретный объект", "slug": "secret-base"},
    )
    assert create_resp.status_code == 201

    # 2. Public endpoint should return 404
    public_resp = await client.get("/api/v1/public/spaces/secret-base")
    assert public_resp.status_code == 404
    assert "not published" in public_resp.json()["detail"]


@pytest.mark.asyncio
async def test_public_space_bundle_when_published(client: AsyncClient, auth_headers: dict):
    # 1. Create space
    create_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Торговый центр Мега", "slug": "tc-mega", "description": "3 этажа магазинов"},
    )
    space_id = create_resp.json()["id"]

    # 2. Add floors
    await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={"floor_number": 1, "title": "1 этаж (Продукты)", "ppm": 25.0},
    )
    await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={"floor_number": 2, "title": "2 этаж (Одежда)", "ppm": 22.5},
    )

    # 3. Publish space
    await client.patch(
        f"/api/v1/spaces/{space_id}/publish",
        headers=auth_headers,
        json={"is_published": True},
    )

    # 4. Fetch public space bundle as anonymous visitor
    public_resp = await client.get("/api/v1/public/spaces/tc-mega")
    assert public_resp.status_code == 200
    bundle = public_resp.json()

    assert bundle["title"] == "Торговый центр Мега"
    assert bundle["slug"] == "tc-mega"
    assert "categories" in bundle
    assert "stand" in bundle["categories"]
    assert "wifi" in bundle["categories"]

    # Check floors in bundle
    assert len(bundle["floors"]) == 2
    assert bundle["floors"][0]["floor_number"] == 1
    assert bundle["floors"][0]["title"] == "1 этаж (Продукты)"
    assert bundle["floors"][0]["ppm"] == 25.0
    assert bundle["floors"][1]["floor_number"] == 2

    # Check Cache-Control header
    assert "public, max-age=60" in public_resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_public_space_preview_by_member_when_unpublished(client: AsyncClient, auth_headers: dict):
    # 1. Create space (unpublished)
    create_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Черновик выставки", "slug": "draft-expo"},
    )
    space_id = create_resp.json()["id"]

    # 2. Add floor
    floor_resp = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=auth_headers,
        json={"floor_number": 1, "title": "1 этаж", "ppm": 20.0},
    )
    floor_id = floor_resp.json()["id"]

    # 3. Add POI
    await client.post(
        f"/api/v1/floors/{floor_id}/pois",
        headers=auth_headers,
        json={"title": "Главный стенд", "category": "stand", "x_coord": 500.0, "y_coord": 400.0},
    )

    # 4. Anonymous request gets 404
    anon_resp = await client.get("/api/v1/public/spaces/draft-expo")
    assert anon_resp.status_code == 404

    # 5. Authenticated member gets 200 with bundle and POIs
    member_resp = await client.get("/api/v1/public/spaces/draft-expo", headers=auth_headers)
    assert member_resp.status_code == 200
    bundle = member_resp.json()
    assert bundle["title"] == "Черновик выставки"
    assert bundle["is_published"] is False
    assert len(bundle["floors"]) == 1
    assert len(bundle["pois"]) == 1
    assert bundle["pois"][0]["title"] == "Главный стенд"
    assert bundle["pois"][0]["x"] == 500.0
    assert bundle["pois"][0]["y"] == 400.0
    assert len(bundle["floors"][0]["pois"]) == 1

