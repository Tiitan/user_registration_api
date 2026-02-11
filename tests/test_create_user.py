from fastapi.testclient import TestClient

from api.app import main
from api.app.dependencies import get_registration_service
from api.app.exceptions.domain import EmailAlreadyExistsError
from api.app.schemas.users import UserResponse


class _FakePool:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


class _SuccessRegistrationService:
    async def register_user(self, *, email: str, password: str) -> UserResponse:
        return UserResponse(id=1, email=email, status="PENDING")


class _DuplicateEmailRegistrationService:
    async def register_user(self, *, email: str, password: str) -> UserResponse:
        raise EmailAlreadyExistsError()


def test_create_user_returns_201(monkeypatch) -> None:
    async def _fake_create_mysql_pool_with_retry() -> _FakePool:
        return _FakePool()

    monkeypatch.setattr(
        "api.app.db.lifespan.create_mysql_pool_with_retry",
        _fake_create_mysql_pool_with_retry,
    )
    main.app.dependency_overrides[get_registration_service] = _SuccessRegistrationService

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/users",
            json={"email": "user@example.com", "password": "StrongPass123"},
        )

    main.app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "email": "user@example.com",
        "status": "PENDING",
    }


def test_create_user_returns_409_when_email_already_exists(monkeypatch) -> None:
    async def _fake_create_mysql_pool_with_retry() -> _FakePool:
        return _FakePool()

    monkeypatch.setattr(
        "api.app.db.lifespan.create_mysql_pool_with_retry",
        _fake_create_mysql_pool_with_retry,
    )
    main.app.dependency_overrides[get_registration_service] = _DuplicateEmailRegistrationService

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/users",
            json={"email": "user@example.com", "password": "StrongPass123"},
        )

    main.app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "error": "email_already_exists",
            "message": "Email is already registered as an active account",
            "details": None,
        }
    }


def test_create_user_rejects_weak_password(monkeypatch) -> None:
    async def _fake_create_mysql_pool_with_retry() -> _FakePool:
        return _FakePool()

    monkeypatch.setattr(
        "api.app.db.lifespan.create_mysql_pool_with_retry",
        _fake_create_mysql_pool_with_retry,
    )
    main.app.dependency_overrides[get_registration_service] = _SuccessRegistrationService

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/users",
            json={"email": "user@example.com", "password": "short1"},
        )

    main.app.dependency_overrides.clear()

    assert response.status_code == 422
