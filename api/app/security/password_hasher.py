"""Shared password hasher instance."""

from argon2 import PasswordHasher

PASSWORD_HASHER = PasswordHasher()
