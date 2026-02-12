"""Integrations with external service providers."""

from api.app.integrations.email_provider_client import EmailProvider, MockEmailProvider

__all__ = ["EmailProvider", "MockEmailProvider"]
