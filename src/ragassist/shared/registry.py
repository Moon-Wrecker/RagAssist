"""Generic thread-safe provider registry.

Supports registering provider factories and instantiating named adapters with settings.
"""

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class ProviderRegistry(Generic[T]):
    """Thread-safe registry mapping provider names to factory functions."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._factories: dict[str, Callable[..., T]] = {}

    def register(self, key: str, factory: Callable[..., T]) -> None:
        """Register a provider factory function under a specific key."""
        normalized_key = key.strip().lower()
        self._factories[normalized_key] = factory

    def create(self, key: str, *args: object, **kwargs: object) -> T:
        """Instantiate a provider using its registered factory."""
        normalized_key = key.strip().lower()
        if normalized_key not in self._factories:
            available = ", ".join(sorted(self._factories.keys())) or "none"
            raise KeyError(
                f"Unknown {self.name} provider '{key}'. Available providers: [{available}]"
            )
        return self._factories[normalized_key](*args, **kwargs)

    def is_registered(self, key: str) -> bool:
        """Check if a provider key is registered."""
        return key.strip().lower() in self._factories

    def available_providers(self) -> list[str]:
        """Return a sorted list of registered provider keys."""
        return sorted(self._factories.keys())

