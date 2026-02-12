"""Email provider abstraction and mock implementation."""

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    """Protocol for sending activation emails."""

    async def send_activation_email(self, *, recipient_email: str, code: str, user_id: int, activation_code_id: int) -> None:
        """Send an activation email message."""
        ...

    async def probe(self) -> None:
        """Verify provider readiness for handling requests."""
        ...


class MockEmailProvider(EmailProvider):
    """In-process provider used for local/testing flows."""

    async def send_activation_email(self, *, recipient_email: str, code: str, user_id: int, activation_code_id: int) -> None:
        """Simulate email delivery without external calls."""
        logger.info("Simulated email provider HTTP request to=%s user_id=%s activation_code_id=%s code=%s",
            recipient_email, user_id, activation_code_id, code)
        await asyncio.sleep(0)

    async def probe(self) -> None:
        """Simulate a provider readiness check."""
        await asyncio.sleep(0)
