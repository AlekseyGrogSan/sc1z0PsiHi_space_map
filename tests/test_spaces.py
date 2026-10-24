import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.space import SpaceRole
from app.models.user import SystemRole, User


@pytest.mark.asyncio
async def test_create_space_and_auto_owner(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={
            "title": "Экспоцентр ТТК 2026",
            "slug": "expocentre-2026",
            "description": "Главный выставочный комплекс",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Экспоцентр ТТК 2026"
    assert data["slug"] == "expocentre-2026"
    assert data["is_published"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_create_duplicate_space_slug_fails(client: AsyncClient, auth_headers: dict):
    payload = {
        "title": "Комплекс 1",
        "slug": "unique-slug-test",
    }
    resp1 = await client.post("/api/v1/spaces", headers=auth_headers, json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/spaces", headers=auth_headers, json=payload)
    assert resp2.status_code == 400
    assert "already exists" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_space_metadata_update_and_publish(client: AsyncClient, auth_headers: dict):
    # 1. Create space
    create_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Отель Плаза", "slug": "hotel-plaza"},
    )
    space_id = create_resp.json()["id"]

    # 2. Update title
    update_resp = await client.patch(
        f"/api/v1/spaces/{space_id}",
        headers=auth_headers,
        json={"title": "Отель Гранд Плаза", "description": "5 звезд"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Отель Гранд Плаза"
    assert update_resp.json()["description"] == "5 звезд"

    # 3. Publish space
    pub_resp = await client.patch(
        f"/api/v1/spaces/{space_id}/publish",
        headers=auth_headers,
        json={"is_published": True},
    )
    assert pub_resp.status_code == 200
    assert pub_resp.json()["is_published"] is True


@pytest.mark.asyncio
async def test_add_member_and_role_permissions(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    # Create colleague user
    colleague = User(
        email="colleague@example.com",
        hashed_password=hash_password("Pass123!"),
        full_name="Colleague Editor",
        system_role=SystemRole.ORGANIZER,
        is_active=True,
    )
    db_session.add(colleague)
    await db_session.commit()
    await db_session.refresh(colleague)
    colleague_headers = {"Authorization": f"Bearer {create_access_token(colleague.id)}"}

    # Owner creates space
    create_resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Конференция", "slug": "conference-2026"},
    )
    space_id = create_resp.json()["id"]

    # Before adding member, colleague cannot add floor
    fail_floor = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=colleague_headers,
        json={"floor_number": 1, "title": "1 этаж"},
    )
    assert fail_floor.status_code == 403

    # Owner adds colleague as EDITOR
    member_resp = await client.post(
        f"/api/v1/spaces/{space_id}/members",
        headers=auth_headers,
        json={"email": "colleague@example.com", "role": "editor"},
    )
    assert member_resp.status_code == 201
    assert member_resp.json()["role"] == "editor"

    # Now colleague can create floor
    floor_resp = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=colleague_headers,
        json={"floor_number": 1, "title": "1 этаж — Главный зал", "ppm": 20.0},
    )
    assert floor_resp.status_code == 201
    assert floor_resp.json()["floor_number"] == 1
    assert floor_resp.json()["title"] == "1 этаж — Главный зал"

    # Creating floor with duplicate floor_number in same space must fail
    dupe_floor = await client.post(
        f"/api/v1/spaces/{space_id}/floors",
        headers=colleague_headers,
        json={"floor_number": 1, "title": "1 этаж дубликат"},
    )
    assert dupe_floor.status_code == 400
    assert "already exists" in dupe_floor.json()["detail"]


@pytest.mark.asyncio
async def test_list_spaces_and_get_space_permissions(client: AsyncClient, auth_headers: dict):
    # 1. Create space
    resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "ТЦ Галерея", "slug": "tc-galeria"},
    )
    space_id = resp.json()["id"]

    # 2. List spaces for user
    list_resp = await client.get("/api/v1/spaces", headers=auth_headers)
    assert list_resp.status_code == 200
    spaces = list_resp.json()
    assert any(s["id"] == space_id for s in spaces)

    # 3. Anonymous visitor accessing unpublished space -> 401
    unauth_resp = await client.get(f"/api/v1/spaces/{space_id}")
    assert unauth_resp.status_code == 401

    # 4. Owner accessing unpublished space -> 200
    owner_resp = await client.get(f"/api/v1/spaces/{space_id}", headers=auth_headers)
    assert owner_resp.status_code == 200

    # 5. Publish space
    await client.patch(
        f"/api/v1/spaces/{space_id}/publish",
        headers=auth_headers,
        json={"is_published": True},
    )

    # 6. Now anonymous visitor can access published space -> 200
    anon_pub_resp = await client.get(f"/api/v1/spaces/{space_id}")
    assert anon_pub_resp.status_code == 200
    assert anon_pub_resp.json()["id"] == space_id


@pytest.mark.asyncio
async def test_delete_space(client: AsyncClient, organizer_user, auth_headers):
    # 1. Create space
    resp = await client.post(
        "/api/v1/spaces",
        headers=auth_headers,
        json={"title": "Временный павильон", "slug": "temp-pavilion"},
    )
    assert resp.status_code == 201
    space_id = resp.json()["id"]

    # 2. Try to delete without auth -> 401
    unauth_resp = await client.delete(f"/api/v1/spaces/{space_id}")
    assert unauth_resp.status_code == 401

    # 3. Delete as owner -> 204
    del_resp = await client.delete(f"/api/v1/spaces/{space_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # 4. Check that space no longer exists -> 404
    get_resp = await client.get(f"/api/v1/spaces/{space_id}", headers=auth_headers)
    assert get_resp.status_code == 404
