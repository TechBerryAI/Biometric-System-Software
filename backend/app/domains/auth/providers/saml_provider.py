"""SAML authentication provider (stub implementation)."""

from __future__ import annotations

from app.domains.auth.providers.base import AuthProvider, AuthProviderConfig, AuthProviderResult


class SamlProvider(AuthProvider):
    def __init__(self, config: AuthProviderConfig) -> None:
        self._config = config

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        if not self._config.enabled:
            raise RuntimeError("SAML provider is not enabled.")
        _ = (state, redirect_uri)
        return f"{self._config.issuer.rstrip('/')}/saml/sso?RelayState={state}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> AuthProviderResult:
        if not self._config.enabled:
            raise RuntimeError("SAML provider is not enabled.")
        _ = (code, redirect_uri)
        raise NotImplementedError("SAML assertion exchange is not configured in this deployment.")

    def validate_token(self, token: str) -> AuthProviderResult:
        if not self._config.enabled:
            raise RuntimeError("SAML provider is not enabled.")
        _ = token
        raise NotImplementedError("SAML assertion validation is not configured in this deployment.")
