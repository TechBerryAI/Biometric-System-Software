"""LDAP authentication provider (stub implementation)."""

from __future__ import annotations

from app.domains.auth.providers.base import AuthProvider, AuthProviderConfig, AuthProviderResult


class LdapProvider(AuthProvider):
    def __init__(self, config: AuthProviderConfig) -> None:
        self._config = config

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        _ = (state, redirect_uri)
        raise NotImplementedError("LDAP uses direct bind authentication, not browser redirect.")

    def exchange_code(self, *, code: str, redirect_uri: str) -> AuthProviderResult:
        _ = (code, redirect_uri)
        raise NotImplementedError("LDAP does not use authorization codes.")

    def validate_token(self, token: str) -> AuthProviderResult:
        _ = token
        raise NotImplementedError("LDAP bind validation is not configured in this deployment.")

    def authenticate(self, *, username: str, password: str) -> AuthProviderResult:
        if not self._config.enabled:
            raise RuntimeError("LDAP provider is not enabled.")
        _ = password
        return AuthProviderResult(
            subject=username,
            email=f"{username}@ldap.local",
            full_name=username,
            groups=[],
        )
