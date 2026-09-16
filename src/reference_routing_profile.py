from __future__ import annotations

"""Reference-derived connection-line style used by every generated diagram.

The six reference sketches are stored in ``assets/routing_references``.  They are
not templates and no component names are encoded into the routing algorithm.
Instead, the common geometric conventions visible in those sketches are expressed
as generic routing preferences here.

Both application workflows ultimately call ``plan_connection_routes`` from
``connection_router.py``.  Therefore this one profile automatically applies to:

* uploaded-sketch diagrams; and
* diagrams generated from Select Components / 2A connections.

Topology remains authoritative.  This profile changes only how a connection is
visually routed after source, target and final component rectangles are known.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_IMAGE_DIR = PROJECT_ROOT / "assets" / "routing_references"

REFERENCE_IMAGES = tuple(
    REFERENCE_IMAGE_DIR / f"reference_{index:02d}.png"
    for index in range(1, 7)
)

# Generic routing style distilled from the references.
REFERENCE_ROUTING_PROFILE = {
    # Safety / correctness always has higher priority than style.
    "hard_component_avoidance": True,
    "preserve_exact_endpoints": True,
    "independent_physical_connections": True,
    "allow_unrelated_shared_segments": False,

    # Reference drawings are overwhelmingly orthogonal and compact.
    "orthogonal_only": True,
    "prefer_straight": True,
    "prefer_single_l": True,
    "prefer_local_corridors": True,
    "prefer_minimum_bends": True,
    "prefer_shortest_clean_route": True,

    # Keep parallel / fan-out paths visually traceable instead of merging them.
    "minimum_connection_gap": 0.155,
    "minimum_component_clearance": 0.115,
    "minimum_port_gap": 0.110,
    "parallel_lane_multiplier": 1.10,

    # Soft route scoring.  Length remains dominant; bends and excessive detours
    # receive enough weight to reproduce the simple reference routing style.
    "bend_penalty": 0.095,
    "excess_detour_penalty": 0.26,

    # Search is intentionally local-first.  Full-canvas A* remains the final
    # safety fallback already present in the project.
    "local_lane_rings": 10,
    "max_lane_candidates_per_axis": 36,
}


def reference_images_available() -> tuple[Path, ...]:
    """Return the reference images that physically exist in the project."""
    return tuple(path for path in REFERENCE_IMAGES if path.is_file())
