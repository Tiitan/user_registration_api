"""Unit tests for registration service port-driven behavior."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from api.app.exceptions import EmailAlreadyExistsError
from api.app.repositories import UserRecord
from api.app.services.registration_service import RegistrationService


class _FakeEmailDispatcher:
    """Capture dispatch calls made by registration service."""

    def __init__(self) -> None:
        """Initialize empty call log."""
        self.calls: list[dict[str, object]] = []

    def dispatch_activation_email(self, *, user_id: int, activation_code_id: int, recipient_email: str, code: str) -> None:
        """Record a dispatch request."""
        self.calls.append(
            {
                "user_id": user_id,
                "activation_code_id": activation_code_id,
                "recipient_email": recipient_email,
                "code": code,
            }
        )


class _FakeRegistrationPort:
    """In-memory registration port fake with configurable behavior."""

    def __init__(self, *, existing_user: UserRecord | None, created_user_id: int, activation_code_id: int) -> None:
        """Configure returned rows and identifiers."""
        self.existing_user = existing_user
        self.created_user_id = created_user_id
        self.activation_code_id = activation_code_id
        self.update_calls: list[dict[str, object]] = []
        self.create_user_calls: list[dict[str, object]] = []
        self.create_code_calls: list[dict[str, object]] = []

    async def get_user_by_email_for_update(self, *, email: str) -> UserRecord | None:
        """Return configured user row."""
        return self.existing_user

    async def create_pending_user(self, *, email: str, password_hash: str) -> int:
        """Record create user call and return configured id."""
        self.create_user_calls.append({"email": email, "password_hash": password_hash})
        return self.created_user_id

    async def update_pending_password(self, *, user_id: int, password_hash: str) -> None:
        """Record password update call."""
        self.update_calls.append({"user_id": user_id, "password_hash": password_hash})

    async def create_activation_code(self, *, user_id: int, code: str) -> int:
        """Record create code call and return configured id."""
        self.create_code_calls.append({"user_id": user_id, "code": code})
        return self.activation_code_id


class _FakeUnitOfWorkFactory:
    """Return a prebuilt registration port inside an async context."""

    def __init__(self, registration_port: _FakeRegistrationPort) -> None:
        """Store fake port."""
        self._registration_port = registration_port

    @asynccontextmanager
    async def registration(self):
        """Yield fake registration port."""
        yield self._registration_port


def test_register_user_creates_new_pending_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Creates user and code when email is not found."""
    monkeypatch.setattr("api.app.services.registration_service.generate_activation_code", lambda: "4321")
    fake_port = _FakeRegistrationPort(existing_user=None, created_user_id=101, activation_code_id=501)
    fake_dispatcher = _FakeEmailDispatcher()
    service = RegistrationService(
        uow_factory=_FakeUnitOfWorkFactory(fake_port),  # type: ignore[arg-type]
        email_dispatcher=fake_dispatcher,  # type: ignore[arg-type]
    )

    response = asyncio.run(service.register_user(email="new@example.com", password="StrongPass123"))

    assert response.id == 101
    assert response.email == "new@example.com"
    assert response.status == "PENDING"
    assert len(fake_port.create_user_calls) == 1
    assert len(fake_port.update_calls) == 0
    assert fake_port.create_code_calls == [{"user_id": 101, "code": "4321"}]
    assert fake_dispatcher.calls == [
        {
            "user_id": 101,
            "activation_code_id": 501,
            "recipient_email": "new@example.com",
            "code": "4321",
        }
    ]


def test_register_user_resets_pending_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Updates pending password and keeps same user id."""
    monkeypatch.setattr("api.app.services.registration_service.generate_activation_code", lambda: "9876")
    existing_user = UserRecord(id=42, email="pending@example.com", password_hash="old", status="PENDING")
    fake_port = _FakeRegistrationPort(existing_user=existing_user, created_user_id=999, activation_code_id=222)
    fake_dispatcher = _FakeEmailDispatcher()
    service = RegistrationService(
        uow_factory=_FakeUnitOfWorkFactory(fake_port),  # type: ignore[arg-type]
        email_dispatcher=fake_dispatcher,  # type: ignore[arg-type]
    )

    response = asyncio.run(service.register_user(email="pending@example.com", password="DifferentPass123"))

    assert response.id == 42
    assert len(fake_port.create_user_calls) == 0
    assert len(fake_port.update_calls) == 1
    assert fake_port.create_code_calls == [{"user_id": 42, "code": "9876"}]
    assert fake_dispatcher.calls[0]["user_id"] == 42


def test_register_user_rejects_active_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raises domain error when existing account is active."""
    monkeypatch.setattr("api.app.services.registration_service.generate_activation_code", lambda: "1111")
    existing_user = UserRecord(id=8, email="active@example.com", password_hash="unused", status="ACTIVE")
    fake_port = _FakeRegistrationPort(existing_user=existing_user, created_user_id=0, activation_code_id=0)
    fake_dispatcher = _FakeEmailDispatcher()
    service = RegistrationService(
        uow_factory=_FakeUnitOfWorkFactory(fake_port),  # type: ignore[arg-type]
        email_dispatcher=fake_dispatcher,  # type: ignore[arg-type]
    )

    with pytest.raises(EmailAlreadyExistsError):
        asyncio.run(service.register_user(email="active@example.com", password="StrongPass123"))

    assert fake_port.create_user_calls == []
    assert fake_port.update_calls == []
    assert fake_port.create_code_calls == []
    assert fake_dispatcher.calls == []
