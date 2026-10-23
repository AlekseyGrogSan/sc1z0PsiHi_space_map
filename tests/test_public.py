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
