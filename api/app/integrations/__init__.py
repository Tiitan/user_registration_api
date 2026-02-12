"""Integrations with external service providers."""

from .email_provider_client import EmailProvider, MockEmailProvider

__all__ = ["EmailProvider", "MockEmailProvider"]
