"""Prometheus metrics exposition for the FastAPI app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import routing as instrumentator_routing
from starlette.routing import Match, Mount

if TYPE_CHECKING:
    from fastapi import FastAPI


def _patch_instrumentator_routing() -> None:
    """Starlette 0.52+ nests included routers without a top-level path attribute."""

    def _get_route_name(scope, routes, route_name=None):  # type: ignore[no-untyped-def]
        for route in routes:
            if not hasattr(route, "matches"):
                nested = getattr(route, "routes", None)
                if nested:
                    nested_name = _get_route_name(scope, nested, route_name)
                    if nested_name:
                        return nested_name
                continue

            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                route_name = getattr(route, "path", route_name)
                child_scope = {**scope, **child_scope}
                nested = getattr(route, "routes", None)
                if isinstance(route, Mount) and nested:
                    child_route_name = _get_route_name(child_scope, nested, route_name)
                    if child_route_name is None:
                        route_name = None
                    elif route_name is not None:
                        route_name += child_route_name
                return route_name
            if match == Match.PARTIAL and route_name is None:
                route_name = getattr(route, "path", None)
        return route_name

    instrumentator_routing._get_route_name = _get_route_name  # type: ignore[attr-defined]


def setup_prometheus_metrics(app: FastAPI) -> None:
    """Expose standard HTTP metrics at /metrics."""
    _patch_instrumentator_routing()
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers={"/metrics"},
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
