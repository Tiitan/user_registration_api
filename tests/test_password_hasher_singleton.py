"""Unit tests for shared password hasher wiring."""

from api.app.security import PASSWORD_HASHER
from api.app.services import ActivationService, RegistrationService


def test_services_use_shared_password_hasher_instance() -> None:
    """Both services should reference the same module-level hasher."""
    registration_service = RegistrationService(db_pool=None, email_dispatcher=None)  # type: ignore[arg-type]
    activation_service = ActivationService(db_pool=None, email_dispatcher=None)  # type: ignore[arg-type]

    assert registration_service._password_hasher is PASSWORD_HASHER
    assert activation_service._password_hasher is PASSWORD_HASHER
