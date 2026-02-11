from datetime import timedelta, timezone

from api.app.config import get_settings
from api.app.services.activation_service import ActivationService

def _create_pending_user(client, *, email: str, password: str) -> None:
    response = client.post("/v1/users", json={"email": email, "password": password})
    assert response.status_code == 201


def test_activate_user_returns_200(client, db_helper) -> None:
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    code = str(db_helper.latest_unused_activation_code("user@example.com")["code"])

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": code})

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"

    user_row = db_helper.fetch_one("SELECT status, activated_at FROM users WHERE email = %s", ("user@example.com",))
    assert user_row is not None
    assert user_row["status"] == "ACTIVE"
    assert user_row["activated_at"] is not None


def test_activate_user_returns_401_for_invalid_credentials(client) -> None:
    _create_pending_user(client, email="user@example.com", password="StrongPass123")

    response = client.post("/v1/users/activate", auth=("user@example.com", "WrongPass123"), json={"code": "1234"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_activate_user_returns_404_when_user_not_found(client) -> None:
    response = client.post("/v1/users/activate", auth=("missing@example.com", "StrongPass123"), json={"code": "1234"})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "user_not_found"


def test_activate_user_returns_409_when_account_is_already_active(client, db_helper) -> None:
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    code = str(db_helper.latest_unused_activation_code("user@example.com")["code"])

    first_activation = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": code})
    assert first_activation.status_code == 200

    second_activation = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": code})
    assert second_activation.status_code == 409
    assert second_activation.json()["detail"]["error"] == "account_already_active"


def test_activate_user_returns_400_when_code_mismatch(client, db_helper) -> None:
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    actual_code = str(db_helper.latest_unused_activation_code("user@example.com")["code"])
    wrong_code = "0000" if actual_code != "0000" else "9999"

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": wrong_code})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "activation_code_mismatch"

    latest_code = db_helper.latest_unused_activation_code("user@example.com")
    assert int(latest_code["attempt_count"]) == 1


def test_activate_user_returns_400_when_attempts_exceeded(client, db_helper) -> None:
    settings = get_settings()
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    actual_code = str(db_helper.latest_unused_activation_code("user@example.com")["code"])
    wrong_code = "0000" if actual_code != "0000" else "9999"

    final_response = None
    for _ in range(settings.activation_code_max_attempts):
        final_response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": wrong_code})

    assert final_response is not None
    assert final_response.status_code == 400
    assert final_response.json()["detail"]["error"] == "activation_code_attempts_exceeded"

    latest_code = db_helper.latest_unused_activation_code("user@example.com")
    assert int(latest_code["attempt_count"]) == settings.activation_code_max_attempts


def test_activate_user_returns_410_when_code_expired(client, db_helper, monkeypatch) -> None:
    settings = get_settings()
    _create_pending_user(client, email="user@example.com", password="StrongPass123")
    client.app.state.email_dispatcher.wait_until_idle(timeout=2.0)

    old_code_row = db_helper.latest_unused_activation_code("user@example.com")
    old_code_id = int(old_code_row["id"])
    old_code = str(old_code_row["code"])
    sent_at = old_code_row["sent_at"]
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    fake_now = sent_at + timedelta(seconds=settings.activation_code_ttl_seconds + 1)

    monkeypatch.setattr(ActivationService, "_utc_now", lambda self: fake_now)

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": old_code})

    assert response.status_code == 410
    assert response.json()["detail"]["error"] == "activation_code_expired"

    new_code_row = db_helper.latest_unused_activation_code("user@example.com")
    assert int(new_code_row["id"]) != old_code_id
    assert int(db_helper.count(
        "SELECT COUNT(*) FROM activation_codes ac JOIN users u ON u.id = ac.user_id WHERE u.email = %s",
        ("user@example.com",),
    )) == 2


def test_activate_user_requires_basic_auth(client) -> None:
    _create_pending_user(client, email="user@example.com", password="StrongPass123")

    response = client.post("/v1/users/activate", json={"code": "1234"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_activate_user_rejects_invalid_code_format(client) -> None:
    _create_pending_user(client, email="user@example.com", password="StrongPass123")

    response = client.post("/v1/users/activate", auth=("user@example.com", "StrongPass123"), json={"code": "abc"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", "code"]
