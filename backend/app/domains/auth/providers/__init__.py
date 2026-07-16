"""Auth provider package."""

from app.domains.auth.providers.base import AuthProvider, AuthProviderConfig, AuthProviderResult

__all__ = ["AuthProvider", "AuthProviderConfig", "AuthProviderResult"]
