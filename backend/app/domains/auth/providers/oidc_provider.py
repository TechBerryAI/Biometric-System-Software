"""OpenID Connect authentication provider (stub implementation)."""

from __future__ import annotations

from urllib.parse import urlencode

from app.domains.auth.providers.base import AuthProvider, AuthProviderConfig, AuthProviderResult


class OidcProvider(AuthProvider):
    def __init__(self, config: AuthProviderConfig) -> None:
        self._config = config

    def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        if not self._config.enabled:
            raise RuntimeError("OIDC provider is not enabled.")
        params = {
            "client_id": self._config.client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        base = self._config.metadata_url or f"{self._config.issuer.rstrip('/')}/authorize"
        return f"{base}?{urlencode(params)}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> AuthProviderResult:
        if not self._config.enabled:
            raise RuntimeError("OIDC provider is not enabled.")
        _ = (code, redirect_uri)
        raise NotImplementedError("OIDC token exchange is not configured in this deployment.")

    def validate_token(self, token: str) -> AuthProviderResult:
        if not self._config.enabled:
            raise RuntimeError("OIDC provider is not enabled.")
        _ = token
        raise NotImplementedError("OIDC token validation is not configured in this deployment.")
