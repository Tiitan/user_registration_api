"""Factory protocol for operation-scoped unit of work contexts."""

from typing import AsyncContextManager, Protocol

from .activation_port import ActivationPort
from .cleanup_port import CleanupPort
from .dispatch_port import DispatchPort
from .registration_port import RegistrationPort


class UnitOfWorkFactory(Protocol):
    """Factory creating operation-scoped transactional ports."""

    def registration(self) -> AsyncContextManager[RegistrationPort]:
        """Create registration transaction context."""
        ...

    def activation(self) -> AsyncContextManager[ActivationPort]:
        """Create activation transaction context."""
        ...

    def dispatch(self) -> AsyncContextManager[DispatchPort]:
        """Create dispatch transaction context."""
        ...

    def cleanup(self) -> AsyncContextManager[CleanupPort]:
        """Create cleanup transaction context."""
        ...
