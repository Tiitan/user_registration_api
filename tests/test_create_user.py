"""Integration tests for user registration endpoint."""

from datetime import datetime, timezone

from argon2 import PasswordHasher
import pytest

from api.app.services.activation_service import ActivationService

pytestmark = pytest.mark.db_cleanup


def test_create_user_returns_201(client, db_helper) -> None:
    """Creates a pending user and activation code."""
    response = client.post("/v1/users", json={"email": "user@example.com", "password": "StrongPass123"})

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["status"] == "PENDING"

    user_row = db_helper.fetch_one("SELECT id, email, status, activated_at FROM users WHERE email = %s", ("user@example.com",))
    assert user_row is not None
    assert int(user_row["id"]) == body["id"]
    assert user_row["status"] == "PENDING"
    assert user_row["activated_at"] is None

    code_row = db_helper.latest_unused_activation_code("user@example.com")
    assert str(code_row["code"]).isdigit()
    assert len(str(code_row["code"])) == 4


def test_create_user_returns_409_when_email_already_active(client, db_helper, monkeypatch) -> None:
    """Rejects registration when the account is already active."""
    create_response = client.post("/v1/users", json={"email": "active@example.com", "password": "StrongPass123"})
    assert create_response.status_code == 201

    code_row = db_helper.latest_unused_activation_code("active@example.com")
    sent_at = code_row["sent_at"]
    fake_now = sent_at if sent_at is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    monkeypatch.setattr(ActivationService, "_now", lambda self: fake_now)
    activate_response = client.post("/v1/users/activate", auth=("active@example.com", "StrongPass123"), json={"code": str(code_row["code"])})
    assert activate_response.status_code == 200

    duplicate_response = client.post("/v1/users", json={"email": "active@example.com", "password": "AnotherPass123"})

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"]["error"] == "email_already_exists"


def test_create_user_rejects_weak_password(client) -> None:
    """Rejects passwords shorter than minimum length."""
    response = client.post("/v1/users", json={"email": "user@example.com", "password": "short1"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", "password"]
    assert detail[0]["type"] == "password_too_short"


@pytest.mark.parametrize("password", ["12345678", "OnlyLetters"])
def test_create_user_rejects_password_without_letter_or_digit(client, password: str) -> None:
    """Rejects passwords that miss required character classes."""
    response = client.post("/v1/users", json={"email": "user@example.com", "password": password})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", "password"]
    assert detail[0]["type"] == "password_not_complex_enough"


def test_create_user_rejects_invalid_email_format(client) -> None:
    """Rejects invalid email formats via schema validation."""
    response = client.post("/v1/users", json={"email": "not-an-email", "password": "StrongPass123"})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", "email"]


def test_create_user_resets_pending_user_and_creates_new_code(client, db_helper) -> None:
    """Resets pending user password and creates a fresh activation code."""
    first_response = client.post("/v1/users", json={"email": "pending@example.com", "password": "StrongPass123"})
    assert first_response.status_code == 201
    first_user_id = int(first_response.json()["id"])

    first_user_row = db_helper.fetch_one("SELECT id, password_hash, status FROM users WHERE email = %s", ("pending@example.com",))
    assert first_user_row is not None
    first_hash = str(first_user_row["password_hash"])
    assert first_user_row["status"] == "PENDING"

    first_code_count = db_helper.count("SELECT COUNT(*) FROM activation_codes ac JOIN users u ON u.id = ac.user_id WHERE u.email = %s", ("pending@example.com",))
    assert first_code_count == 1

    second_response = client.post("/v1/users", json={"email": "pending@example.com", "password": "DifferentPass123"})
    assert second_response.status_code == 201
    assert int(second_response.json()["id"]) == first_user_id

    second_user_row = db_helper.fetch_one("SELECT id, password_hash, status FROM users WHERE email = %s", ("pending@example.com",))
    assert second_user_row is not None
    second_hash = str(second_user_row["password_hash"])
    assert second_user_row["status"] == "PENDING"
    assert second_hash != first_hash

    hasher = PasswordHasher()
    assert hasher.verify(second_hash, "DifferentPass123")

    second_code_count = db_helper.count("SELECT COUNT(*) FROM activation_codes ac JOIN users u ON u.id = ac.user_id WHERE u.email = %s", ("pending@example.com",))
    assert second_code_count == 2
