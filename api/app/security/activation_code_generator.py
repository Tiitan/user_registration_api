"""Activation code generation helpers."""

import secrets

_ACTIVATION_CODE_DIGITS = "0123456789"
_ACTIVATION_CODE_LENGTH = 4


def generate_activation_code() -> str:
    """Return a cryptographically secure 4-digit activation code."""
    return "".join(secrets.choice(_ACTIVATION_CODE_DIGITS) for _ in range(_ACTIVATION_CODE_LENGTH))
