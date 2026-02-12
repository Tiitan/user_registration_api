import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    async def send_activation_email(self, *, recipient_email: str, code: str, user_id: int, activation_code_id: int) -> None:
        ...


class MockEmailProvider(EmailProvider):
    async def send_activation_email(self, *, recipient_email: str, code: str, user_id: int, activation_code_id: int) -> None:
        logger.info("Simulated email provider HTTP request to=%s user_id=%s activation_code_id=%s code=%s",
            recipient_email, user_id, activation_code_id, code)
        await asyncio.sleep(0)
