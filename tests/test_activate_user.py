from fastapi.testclient import TestClient

from api.app import main
from api.app.dependencies import get_activation_service
from api.app.exceptions.domain import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    ActivationCodeNotDeliveredError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from api.app.schemas.users import ActivatedUserResponse


class _FakePool:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


class _SuccessActivationService:
    async def activate_user(self, *, email: str, password: str, code: str) -> ActivatedUserResponse:
        return ActivatedUserResponse(id=1, email=email, status="ACTIVE")


class _ErrorActivationService:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def activate_user(self, *, email: str, password: str, code: str) -> ActivatedUserResponse:
        raise self._error


def _patch_pool(monkeypatch) -> None:
    async def _fake_create_mysql_pool_with_retry() -> _FakePool:
        return _FakePool()

    monkeypatch.setattr("api.app.db.lifespan.create_mysql_pool_with_retry", _fake_create_mysql_pool_with_retry)


def test_activate_user_returns_200(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = _SuccessActivationService

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"id": 1, "email": "user@example.com", "status": "ACTIVE"}


def test_activate_user_returns_401_for_invalid_credentials(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = lambda: _ErrorActivationService(InvalidCredentialsError())

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "wrong"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_activate_user_returns_404_when_user_not_found(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = lambda: _ErrorActivationService(UserNotFoundError())

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("missing@example.com", "StrongPass123"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "user_not_found"


def test_activate_user_returns_409_when_account_is_already_active(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = lambda: _ErrorActivationService(AccountAlreadyActiveError())

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "account_already_active"


def test_activate_user_returns_400_when_code_not_delivered(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = lambda: _ErrorActivationService(ActivationCodeNotDeliveredError())

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "activation_code_not_delivered"


def test_activate_user_returns_410_when_code_expired(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = lambda: _ErrorActivationService(ActivationCodeExpiredError())

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 410
    assert response.json()["detail"]["error"] == "activation_code_expired"


def test_activate_user_returns_400_when_code_mismatch(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = lambda: _ErrorActivationService(ActivationCodeMismatchError())

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "activation_code_mismatch"


def test_activate_user_returns_400_when_attempts_exceeded(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = lambda: _ErrorActivationService(ActivationCodeAttemptsExceededError())

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "activation_code_attempts_exceeded"


def test_activate_user_requires_basic_auth(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = _SuccessActivationService

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", json={"code": "1234"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_activate_user_rejects_invalid_code_format(monkeypatch) -> None:
    _patch_pool(monkeypatch)
    main.app.dependency_overrides[get_activation_service] = _SuccessActivationService

    with TestClient(main.app) as client:
        response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "abc"})

    main.app.dependency_overrides.clear()

    assert response.status_code == 422
