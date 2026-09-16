from __future__ import annotations

"""Compatibility facade for the project's single connection router."""

from .connection_router import (
    Box,
    ConnectionRouter,
    Point,
    PortAssignment,
    ReservedRoute,
    RoutingSpace,
    SIDES,
    analyze_routing_space,
    plan_connection_routes,
)

__all__ = [
    "Point",
    "Box",
    "SIDES",
    "RoutingSpace",
    "PortAssignment",
    "ReservedRoute",
    "ConnectionRouter",
    "analyze_routing_space",
    "plan_connection_routes",
]
