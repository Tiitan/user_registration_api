class EmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class AccountAlreadyActiveError(Exception):
    pass


class ActivationCodeExpiredError(Exception):
    pass


class ActivationCodeMismatchError(Exception):
    pass


class ActivationCodeAttemptsExceededError(Exception):
    pass
