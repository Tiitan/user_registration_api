"""Domain-level exceptions exposed by services."""

class EmailAlreadyExistsError(Exception):
    """Raised when trying to register an already active email."""

    pass


class InvalidCredentialsError(Exception):
    """Raised when authentication credentials are invalid."""

    pass


class UserNotFoundError(Exception):
    """Raised when the requested user does not exist."""

    pass


class AccountAlreadyActiveError(Exception):
    """Raised when activation is requested for an active account."""

    pass


class ActivationCodeExpiredError(Exception):
    """Raised when an activation code has expired."""

    pass


class ActivationCodeMismatchError(Exception):
    """Raised when a provided activation code does not match."""

    pass


class ActivationCodeAttemptsExceededError(Exception):
    """Raised when maximum activation code attempts are reached."""

    pass
