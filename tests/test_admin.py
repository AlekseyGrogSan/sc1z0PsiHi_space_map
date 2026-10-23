import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_admin_list_users_allowed_for_superadmin(
    client: AsyncClient, superadmin_headers: dict
):
    response = await client.get("/api/v1/admin/users", headers=superadmin_headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert len(users) >= 1


@pytest.mark.asyncio
async def test_admin_list_users_forbidden_for_organizer(
    client: AsyncClient, auth_headers: dict
):
    response = await client.get("/api/v1/admin/users", headers=auth_headers)
    assert response.status_code == 403
    assert "Superadmin" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_toggle_user_status(
    client: AsyncClient,
    superadmin_headers: dict,
    organizer_user: User,
):
    # Deactivate organizer
    response = await client.patch(
        f"/api/v1/admin/users/{organizer_user.id}/status",
        headers=superadmin_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Attempt login with deactivated user
    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": organizer_user.email, "password": "Password123!"},
    )
    assert login_resp.status_code == 403
    assert "deactivated" in login_resp.json()["detail"]

    # Reactivate organizer
    reactivate_resp = await client.patch(
        f"/api/v1/admin/users/{organizer_user.id}/status",
        headers=superadmin_headers,
        json={"is_active": True},
    )
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_superadmin_cannot_deactivate_self(
    client: AsyncClient,
    superadmin_headers: dict,
    superadmin_user: User,
):
    response = await client.patch(
        f"/api/v1/admin/users/{superadmin_user.id}/status",
        headers=superadmin_headers,
        json={"is_active": False},
    )
    assert response.status_code == 400
    assert "own administrator account" in response.json()["detail"]
