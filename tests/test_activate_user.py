"""Integration tests for user activation endpoint."""

from datetime import datetime, timedelta, timezone

import pytest

from api.app.config import get_settings
from api.app.services import ActivationService

pytestmark = pytest.mark.db_cleanup


def _create_pending_user(client, *, email: str, password: str) -> None:
    """Create a pending user fixture via API."""
    response = client.post("/v1/users", json={"email": email, "password": password})
    assert response.status_code == 201


def _pin_now_to_latest_code_sent_at(*, monkeypatch, db_helper, email: str) -> None:
    """Pin service clock to latest code sent_at to keep code unexpired."""
    sent_at = db_helper.latest_unused_activation_code(email)["sent_at"]
    fake_now = sent_at if sent_at is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    monkeypatch.setattr(ActivationService, "_now", lambda self: fake_now)


def test_activate_user_returns_200(client, db_helper, monkeypatch) -> None:
    """Activates a pending user with valid credentials and code."""
    code = "1234"
    monkeypatch.setattr("api.app.services.registration_service.generate_activation_code", lambda: code)
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    _pin_now_to_latest_code_sent_at(monkeypatch=monkeypatch, db_helper=db_helper, email="user@example.com")

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": code})

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"

    user_row = db_helper.fetch_one("SELECT status, activated_at FROM users WHERE email = %s", ("user@example.com",))
    assert user_row is not None
    assert user_row["status"] == "ACTIVE"
    assert user_row["activated_at"] is not None


def test_activate_user_returns_401_for_invalid_credentials(client) -> None:
    """Rejects activation when password is invalid."""
    _create_pending_user(client, email="user@example.com", password="StrongPass123")

    response = client.post("/v1/users/activate", auth=("user@example.com", "WrongPass123"), json={"code": "1234"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_activate_user_returns_404_when_user_not_found(client) -> None:
    """Returns not found for unknown users."""
    response = client.post("/v1/users/activate", auth=("missing@example.com", "StrongPass123"), json={"code": "1234"})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "user_not_found"


def test_activate_user_returns_409_when_account_is_already_active(client, db_helper, monkeypatch) -> None:
    """Rejects activation when account is already active."""
    code = "1234"
    monkeypatch.setattr("api.app.services.registration_service.generate_activation_code", lambda: code)
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    _pin_now_to_latest_code_sent_at(monkeypatch=monkeypatch, db_helper=db_helper, email="user@example.com")

    first_activation = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": code})
    assert first_activation.status_code == 200

    second_activation = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": code})
    assert second_activation.status_code == 409
    assert second_activation.json()["detail"]["error"] == "account_already_active"


def test_activate_user_returns_400_when_code_mismatch(client, db_helper, monkeypatch) -> None:
    """Increments attempts and returns mismatch for wrong code."""
    code = "1234"
    monkeypatch.setattr("api.app.services.registration_service.generate_activation_code", lambda: code)
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    _pin_now_to_latest_code_sent_at(monkeypatch=monkeypatch, db_helper=db_helper, email="user@example.com")
    wrong_code = "0000"

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": wrong_code})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "activation_code_mismatch"

    latest_code = db_helper.latest_unused_activation_code("user@example.com")
    assert int(latest_code["attempt_count"]) == 1


def test_activate_user_returns_400_when_attempts_exceeded(client, db_helper, monkeypatch) -> None:
    """Returns attempts exceeded after maximum failed tries."""
    settings = get_settings()
    code = "1234"
    monkeypatch.setattr("api.app.services.registration_service.generate_activation_code", lambda: code)
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    _pin_now_to_latest_code_sent_at(monkeypatch=monkeypatch, db_helper=db_helper, email="user@example.com")
    wrong_code = "0000"

    final_response = None
    for _ in range(settings.activation_code_max_attempts):
        final_response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": wrong_code})

    assert final_response is not None
    assert final_response.status_code == 400
    assert final_response.json()["detail"]["error"] == "activation_code_attempts_exceeded"

    latest_code = db_helper.latest_unused_activation_code("user@example.com")
    assert int(latest_code["attempt_count"]) == settings.activation_code_max_attempts


def test_activate_user_returns_410_when_code_expired(client, db_helper, monkeypatch) -> None:
    """Returns expired and issues a replacement code when TTL is exceeded."""
    settings = get_settings()
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    client.app.state.email_dispatcher.wait_until_idle(timeout=2.0)

    old_code_row = db_helper.latest_unused_activation_code("user@example.com")
    old_code_id = int(old_code_row["id"])
    old_code = str(old_code_row["code"])
    sent_at = old_code_row["sent_at"]
    fake_now = sent_at + timedelta(seconds=settings.activation_code_ttl_seconds + 1)

    monkeypatch.setattr(ActivationService, "_now", lambda self: fake_now)

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": old_code})

    assert response.status_code == 410
    assert response.json()["detail"]["error"] == "activation_code_expired"

    new_code_row = db_helper.latest_unused_activation_code("user@example.com")
    assert int(new_code_row["id"]) != old_code_id
    assert int(db_helper.count(
        "SELECT COUNT(*) FROM activation_codes ac JOIN users u ON u.id = ac.user_id WHERE u.email = %s",
        ("user@example.com",),
    )) == 2


def test_is_code_expired_raises_for_timezone_aware_sent_at(client) -> None:
    """Fails fast when sent_at is timezone-aware in local-time mode."""
    service = ActivationService(
        db_pool=client.app.state.db_pool,
        email_dispatcher=client.app.state.email_dispatcher,
    )
    aware_sent_at = datetime.now(timezone.utc)

    with pytest.raises(RuntimeError, match="Timezone-aware activation sent_at is unsupported"):
        service._is_code_expired(aware_sent_at)


def test_activate_user_requires_basic_auth(client) -> None:
    """Requires HTTP Basic credentials for activation."""
    _create_pending_user(client, email="user@example.com", password="StrongPass123")

    response = client.post("/v1/users/activate", json={"code": "1234"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_activate_user_rejects_invalid_code_format(client) -> None:
    """Rejects activation codes that are not four digits."""
    _create_pending_user(client, email="user@example.com", password="StrongPass123")

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "abc"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", "code"]
