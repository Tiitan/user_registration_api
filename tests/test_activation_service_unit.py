"""Unit tests for activation service port-driven behavior."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest

from api.app.config import get_settings
from api.app.exceptions import (
    AccountAlreadyActiveError,
    ActivationCodeAttemptsExceededError,
    ActivationCodeExpiredError,
    ActivationCodeMismatchError,
    UserNotFoundError,
)
from api.app.repositories import ActivationCodeRecord, UserRecord
from api.app.security import PASSWORD_HASHER
from api.app.services.activation_service import ActivationService

_VALID_PASSWORD = "StrongPass123"
_VALID_PASSWORD_HASH = PASSWORD_HASHER.hash(_VALID_PASSWORD)


class _FakeEmailDispatcher:
    """Capture dispatch calls made by activation service."""

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


class _FakeActivationPort:
    """In-memory activation port fake with configurable behavior."""

    def __init__(self, *, user_row: UserRecord | None, code_row: ActivationCodeRecord | None) -> None:
        """Configure user and activation code rows."""
        self.user_row = user_row
        self.code_row = code_row
        self.get_latest_calls = 0
        self.create_code_calls: list[dict[str, object]] = []
        self.increment_attempt_calls: list[int] = []
        self.mark_used_calls: list[int] = []
        self.mark_active_calls: list[int] = []

    async def get_user_by_email_for_update(self, *, email: str) -> UserRecord | None:
        """Return configured user row."""
        return self.user_row

    async def get_latest_activation_code_for_update(self, *, user_id: int) -> ActivationCodeRecord | None:
        """Return configured activation code row."""
        self.get_latest_calls += 1
        return self.code_row

    async def create_activation_code(self, *, user_id: int, code: str) -> int:
        """Record replacement code creation."""
        self.create_code_calls.append({"user_id": user_id, "code": code})
        return 999

    async def increment_activation_attempt_count(self, *, activation_code_id: int) -> None:
        """Record attempt counter increment."""
        self.increment_attempt_calls.append(activation_code_id)

    async def mark_activation_code_used(self, *, activation_code_id: int) -> None:
        """Record used marker update."""
        self.mark_used_calls.append(activation_code_id)

    async def mark_user_as_active(self, *, user_id: int) -> None:
        """Record user activation update."""
        self.mark_active_calls.append(user_id)


class _FakeUnitOfWorkFactory:
    """Return a prebuilt activation port inside an async context."""

    def __init__(self, activation_port: _FakeActivationPort) -> None:
        """Store fake port."""
        self._activation_port = activation_port

    @asynccontextmanager
    async def activation(self):
        """Yield fake activation port."""
        yield self._activation_port


def _service_with_port(port: _FakeActivationPort, dispatcher: _FakeEmailDispatcher) -> ActivationService:
    """Build service with fake dependencies."""
    return ActivationService(
        uow_factory=_FakeUnitOfWorkFactory(port),  # type: ignore[arg-type]
        email_dispatcher=dispatcher,  # type: ignore[arg-type]
    )


def _pending_user(email: str = "user@example.com") -> UserRecord:
    """Build a valid pending user row."""
    return UserRecord(id=11, email=email, password_hash=_VALID_PASSWORD_HASH, status="PENDING")


def test_activate_user_raises_user_not_found() -> None:
    """Raises not-found when no user matches the email."""
    port = _FakeActivationPort(user_row=None, code_row=None)
    dispatcher = _FakeEmailDispatcher()
    service = _service_with_port(port, dispatcher)

    with pytest.raises(UserNotFoundError):
        asyncio.run(service.activate_user(email="missing@example.com", password=_VALID_PASSWORD, code="1234"))

    assert dispatcher.calls == []


def test_activate_user_raises_already_active() -> None:
    """Raises conflict when user is already active."""
    active_user = UserRecord(id=10, email="active@example.com", password_hash=_VALID_PASSWORD_HASH, status="ACTIVE")
    port = _FakeActivationPort(user_row=active_user, code_row=None)
    dispatcher = _FakeEmailDispatcher()
    service = _service_with_port(port, dispatcher)

    with pytest.raises(AccountAlreadyActiveError):
        asyncio.run(service.activate_user(email="active@example.com", password=_VALID_PASSWORD, code="1234"))

    assert port.get_latest_calls == 0
    assert dispatcher.calls == []


def test_activate_user_raises_code_mismatch_and_increments_attempts() -> None:
    """Raises mismatch and increments attempt count for wrong code."""
    code_row = ActivationCodeRecord(id=55, user_id=11, code="1234", sent_at=None, attempt_count=0)
    port = _FakeActivationPort(user_row=_pending_user(), code_row=code_row)
    dispatcher = _FakeEmailDispatcher()
    service = _service_with_port(port, dispatcher)

    with pytest.raises(ActivationCodeMismatchError):
        asyncio.run(service.activate_user(email="user@example.com", password=_VALID_PASSWORD, code="0000"))

    assert port.increment_attempt_calls == [55]
    assert port.mark_used_calls == []
    assert port.mark_active_calls == []


def test_activate_user_raises_attempts_exceeded_when_limit_reached() -> None:
    """Raises attempts exceeded without increment when max already reached."""
    settings = get_settings()
    code_row = ActivationCodeRecord(
        id=56,
        user_id=11,
        code="1234",
        sent_at=None,
        attempt_count=settings.activation_code_max_attempts,
    )
    port = _FakeActivationPort(user_row=_pending_user(), code_row=code_row)
    dispatcher = _FakeEmailDispatcher()
    service = _service_with_port(port, dispatcher)

    with pytest.raises(ActivationCodeAttemptsExceededError):
        asyncio.run(service.activate_user(email="user@example.com", password=_VALID_PASSWORD, code="0000"))

    assert port.increment_attempt_calls == []


def test_activate_user_raises_expired_and_dispatches_new_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Creates and dispatches replacement code when current code is expired."""
    sent_at = datetime(2026, 1, 1, 12, 0, 0)
    code_row = ActivationCodeRecord(id=57, user_id=11, code="1234", sent_at=sent_at, attempt_count=0)
    port = _FakeActivationPort(user_row=_pending_user(), code_row=code_row)
    dispatcher = _FakeEmailDispatcher()
    service = _service_with_port(port, dispatcher)
    monkeypatch.setattr("api.app.services.activation_service.generate_activation_code", lambda: "7777")
    service._now = lambda: sent_at + timedelta(seconds=service._activation_code_ttl_seconds + 1)  # type: ignore[method-assign]

    with pytest.raises(ActivationCodeExpiredError):
        asyncio.run(service.activate_user(email="user@example.com", password=_VALID_PASSWORD, code="1234"))

    assert port.create_code_calls == [{"user_id": 11, "code": "7777"}]
    assert dispatcher.calls == [
        {
            "user_id": 11,
            "activation_code_id": 999,
            "recipient_email": "user@example.com",
            "code": "7777",
        }
    ]
    assert port.increment_attempt_calls == []
    assert port.mark_used_calls == []
    assert port.mark_active_calls == []


def test_activate_user_marks_code_used_and_user_active_on_success() -> None:
    """Activates account when credentials and code are valid."""
    code_row = ActivationCodeRecord(id=58, user_id=11, code="1234", sent_at=None, attempt_count=0)
    port = _FakeActivationPort(user_row=_pending_user(), code_row=code_row)
    dispatcher = _FakeEmailDispatcher()
    service = _service_with_port(port, dispatcher)

    response = asyncio.run(service.activate_user(email="user@example.com", password=_VALID_PASSWORD, code="1234"))

    assert response.id == 11
    assert response.email == "user@example.com"
    assert response.status == "ACTIVE"
    assert port.mark_used_calls == [58]
    assert port.mark_active_calls == [11]
    assert dispatcher.calls == []
