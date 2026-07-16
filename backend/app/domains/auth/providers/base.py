"""External authentication provider interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AuthProviderResult:
    subject: str
    email: str
    full_name: str | None = None
    groups: list[str] = field(default_factory=list)
    raw_claims: dict[str, str | int | bool | list[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuthProviderConfig:
    issuer: str
    client_id: str
    client_secret: str | None = None
    metadata_url: str | None = None
    enabled: bool = False


class AuthProvider(ABC):
    @abstractmethod
    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Return provider-specific authorization URL for browser redirect."""

    @abstractmethod
    def exchange_code(self, *, code: str, redirect_uri: str) -> AuthProviderResult:
        """Exchange authorization code for authenticated identity."""

    @abstractmethod
    def validate_token(self, token: str) -> AuthProviderResult:
        """Validate bearer/id token and return normalized identity."""
