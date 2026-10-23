import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_first_user_becomes_superadmin(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "first_user@test.com",
            "password": "Password123!",
            "full_name": "First User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "first_user@test.com"
    assert data["system_role"] == "superadmin"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_subsequent_user_becomes_organizer(client: AsyncClient):
    # Register first user
    await client.post(
        "/api/v1/auth/register",
        json={"email": "first@test.com", "password": "Password123!"},
    )
    # Register second user
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "second@test.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    assert response.json()["system_role"] == "organizer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dupe@test.com", "password": "Password123!"}
    resp1 = await client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "already exists" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login_test@test.com", "password": "ValidPassword123!"},
    )

    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "login_test@test.com", "password": "ValidPassword123!"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wrong_pw@test.com", "password": "ValidPassword123!"},
    )

    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "wrong_pw@test.com", "password": "WrongPassword"},
    )
    assert login_resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh_test@test.com", "password": "Password123!"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "refresh_test@test.com", "password": "Password123!"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "organizer@example.com"
    assert "accessible_spaces" in data
