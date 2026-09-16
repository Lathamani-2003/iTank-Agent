from __future__ import annotations

import math
import os
import time
from copy import deepcopy
from difflib import SequenceMatcher
from io import BytesIO

from google.genai import types

try:
    import numpy as np
except Exception:  # numpy is optional; the pipeline still works without it.
    np = None

from .models import DiagramEdge, DiagramNode, DiagramPoint, DiagramSpec


# =============================================================================
# AGENT 1: EXHAUSTIVE COMPONENT INVENTORY + PRELIMINARY TRACE
# =============================================================================

INVENTORY_AGENT_PROMPT = r"""
You are an Exact Hand-Sketch Engineering Inventory Agent for an industrial
water-automation diagram system.

You receive TWO images of the SAME drawing:
1. ORIGINAL hand-drawn sketch
2. OpenCV-enhanced copy of the SAME sketch

Use BOTH images together:
- ORIGINAL is the semantic authority for handwritten names, equipment meaning,
  arrowheads, and ambiguous crossings.
- OpenCV-enhanced copy is the geometric authority when pipe strokes, branches,
  continuations, and box boundaries are clearer there.

Do not treat the OpenCV image as a different diagram. It is the same drawing.

===============================================================================
A. FIRST PRIORITY: COMPLETE COMPONENT INVENTORY
===============================================================================

Inventory EVERY physical component visible anywhere in the full uploaded image.
Do not stop after the obvious central group. Scan top-to-bottom and left-to-right.

Physical components include:
- bore wells
- sumps
- OHT / overhead tanks
- motors / pumps
- valves
- sensors
- controllers
- external sources such as lorry water
- other actual equipment or named destination/source blocks

Allowed node_type:
bore, sump, oht, motor, valve, sensor, controller, junction, other

PIPELINES ARE EDGES. Never create a node called pipe or pipeline.
Text written beside a pipe is not a component.

For each physical component preserve:
- a stable unique lowercase_snake_case id
- the most complete readable label visible in the drawing
- relative center x/y in the RAW uploaded image coordinate system
- approximate visible width/height
- useful short details such as capacity/distance when they visibly belong to it

Coordinates are normalized 0..1 from the exact uploaded image orientation:
x=0 left, x=1 right, y=0 top, y=1 bottom.
Do not rotate coordinates merely because handwriting is sideways.

===============================================================================
B. JUNCTION INVENTORY
===============================================================================

Create a junction node ONLY for a visibly shared branch/split/merge point where
one physical pipe becomes multiple physical paths or multiple paths visibly join.
Do NOT create junctions at ordinary line crossings that do not visibly connect.

===============================================================================
C. PRELIMINARY PIPE TRACE
===============================================================================

Also trace every pipe you can clearly establish. This preliminary edge list is a
safety copy for the second dedicated topology pass.

For each visible pipe preserve:
- source and target physical endpoint node ids
- source_side and target_side
- source_anchor and target_anchor: exact normalized touch points on component
  boundaries whenever visible
- ordered major bend waypoints, including intermediate bends needed to keep nearby
  or parallel pipes visually distinct
- visible direction / arrow orientation
- pipe size and line label
- locked_route=true (confirmed physical connection; preserve topology/endpoints/sides, while final renderer may create a clean Manhattan route after layout)

NEVER invent, remove, merge, shorten, or logically redesign a connection.
Crossing lines are not connected unless the image visibly shows a join.
Parallel pipes remain separate physical edges.

===============================================================================
D. FINAL SELF-CHECK
===============================================================================

Before returning, scan the full image again and verify that no physical component
was omitted simply because it is near an edge, below another block, or connected
by a long outer pipe.

Return ONLY DiagramSpec structured data.
"""


# =============================================================================
# AGENT 2: NODE-LOCKED COMPLETE TOPOLOGY TRACE
# =============================================================================

TOPOLOGY_TRACE_PROMPT = r"""
You are an Exact Pipeline Topology Tracing Agent.

You receive:
1. ORIGINAL hand-drawn sketch
2. OpenCV-enhanced copy of the SAME sketch
3. a LOCKED COMPONENT MANIFEST extracted from those images

Use BOTH images together:
- ORIGINAL is authoritative for names, arrows, equipment meaning, and whether a
  crossing is actually connected.
- OpenCV-enhanced image is authoritative for following faint pipe strokes,
  branches, long continuations, and exact visible route geometry.

The component manifest is a stable identity list. Reuse its physical node ids.
Do not casually rename, delete, merge, or substitute those physical nodes.
You MAY add a missing physical node only when it is clearly visible in BOTH the
original/enhanced evidence and the manifest genuinely omitted it.
You MAY add junction nodes where a real visible branch/split/merge requires them.

===============================================================================
A. TRACE EVERY PHYSICAL CONNECTION - HIGHEST PRIORITY
===============================================================================

Trace EVERY visible pipeline independently from one real endpoint to the other.
Follow the ink/line continuously. Do not infer based on engineering expectations.

For every edge:
- source = exact endpoint node id at the first end
- target = exact endpoint node id at the other end
- direction = source_to_target / target_to_source / unknown from visible arrows
- source_side = exact side touched: left/right/top/bottom
- target_side = exact side touched: left/right/top/bottom
- source_anchor = normalized exact touch point on source boundary when visible
- target_anchor = normalized exact touch point on target boundary when visible
- waypoints = ordered major visible bends/turns in image coordinates
- pipe_size / label = only text visibly belonging to that pipe
- locked_route = true

Source/target describe the two traced physical endpoints. Direction is stored
separately. Never swap endpoints merely to make direction convenient.

===============================================================================
B. BRANCHES / MANIFOLDS
===============================================================================

At every visible branch or manifold:
1. identify the exact shared branch point
2. create/reuse one junction node at that visible point
3. terminate the incoming physical segment at that junction
4. create separate outgoing physical edges from the same junction

Do not replace a branch by several guessed direct component-to-component edges.
Do not merge independent parallel lines into one edge.

===============================================================================
C. CROSSINGS
===============================================================================

If two lines merely cross and do not visibly join, keep them as two independent
pipes. Do not create a junction there. Use the ORIGINAL image to resolve whether
there is a dot/T-join/continuous branch or just a crossing.

===============================================================================
D. LARGE-DIAGRAM TRACE PROCEDURE
===============================================================================

Perform this exhaustive internal check before returning:
1. Start with each physical component in the locked manifest.
2. For that component, inspect every side and count each separate pipe touching it.
3. Trace each touching pipe stroke until its actual other endpoint or junction.
4. Repeat for every component, including those at image edges.
5. Reconcile duplicate observations of the same physical pipe only after both
   endpoint traces agree.
6. Recheck the central/high-density manifold area separately.
7. Recheck long outer-loop pipes separately.
8. Recheck all motor/pump connections separately.
9. Recheck all sump and overhead-tank connections separately.
10. Verify every visible pipe has exactly one edge representation unless there are
    genuinely multiple parallel physical pipes.
11. Verify no returned edge lacks visible image support.
12. Verify source/target, direction, anchors, and bends match the drawing.

Do not beautify or redesign the GRAPH. The final renderer will handle visual spacing.
The critical output is the COMPLETE PHYSICAL TOPOLOGY: every real pipe, every branch,
every parallel pipe, every endpoint and every crossing-vs-junction decision.
Return ONLY the complete DiagramSpec.
"""


# =============================================================================
# AGENT 3: IMAGE-BASED TOPOLOGY AUDIT
# =============================================================================

VERIFY_AGENT_PROMPT = r"""
You are the Final Exact Connection Auditor.

You receive:
1. ORIGINAL hand-drawn sketch
2. OpenCV-enhanced copy of the same sketch
3. a candidate DiagramSpec

The task is NOT to redesign the diagram. Audit only topology and route evidence.

Use the ORIGINAL image for semantic truth and connection-vs-crossing decisions.
Use the OpenCV-enhanced image to follow faint/long pipe strokes and branches.

Keep existing physical component identities stable. You may add a missing physical
component only if it is unmistakably visible, and may add junction nodes only at
real branch/split/merge points.

For EACH physical pipe independently verify:
- exact source endpoint
- exact target endpoint
- exact visible arrow direction
- source_side / target_side
- source_anchor / target_anchor
- branch/junction membership
- crossing-without-connection cases
- ordered major waypoints
- pipe size / label
- missing edge
- invented edge
- accidentally merged parallel edges

Every visible pipe must have exactly one representation, except genuinely parallel
physical pipes which must each remain separate. Every returned edge must be visibly
supported by the images.

Do not shorten, reroute, merge, or simplify for aesthetics.
Return ONLY the complete corrected DiagramSpec.
"""


CONNECTION_CENSUS_PROMPT = r"""
You are a connection-census auditor for a dense engineering sketch.

You receive the ORIGINAL image, an enhanced copy, a locked component manifest, and
an existing candidate DiagramSpec. Your only job is RECALL: find visible physical
pipes that are missing from the candidate. Do not redesign the diagram.

For every physical component in the manifest inspect LEFT, RIGHT, TOP and BOTTOM
sides independently. Count every distinct pipe stroke touching that side. Treat two
parallel strokes with the same endpoints as TWO physical edges unless the image
proves they are the same stroke. Never use engineering expectation to omit a line. Follow
that stroke until the next physical component or a visible junction. Record each
physical connection as an edge with exact source/target, sides, anchors and ordered
waypoints. Parallel pipes are separate edges. Crossings without a visible join are
not junctions.

Return the COMPLETE DiagramSpec, including all candidate edges plus every additional
visible edge you can establish. Never delete an existing candidate edge merely
because another edge looks similar.
"""

RETRY_PROMPT = r"""
Re-read BOTH images carefully. Return a compact but COMPLETE DiagramSpec.
The original supplies semantic meaning; the OpenCV image helps trace geometry.

Priority:
1. complete physical component inventory
2. every visible pipe endpoint pair
3. exact branch/junction membership
4. exact crossing-without-connection behavior
5. exact source/target sides and endpoint anchors
6. exact visible flow direction
7. ordered major bends/waypoints
8. pipe sizes and labels

Do not invent, omit, simplify, merge, or reroute any physical connection.
Every edge must have locked_route=true (confirmed physical connection; preserve topology/endpoints/sides, while final renderer may create a clean Manhattan route after layout).
"""

# Backward-compatible public name used by earlier project code/tests.
SKETCH_AGENT_PROMPT = INVENTORY_AGENT_PROMPT


# =============================================================================
# IMAGE CONVERSION
# =============================================================================

def _image_to_part(image) -> types.Part:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/png")


# =============================================================================
# STRUCTURED RESPONSE PARSING
# =============================================================================

def _strip_fence(text: str) -> str:
    value = (text or "").strip()
    if value.startswith("```json"):
        value = value[7:]
    elif value.startswith("```"):
        value = value[3:]
    if value.endswith("```"):
        value = value[:-3]
    return value.strip()


def _parse_diagram(response) -> DiagramSpec:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, DiagramSpec):
        return parsed
    if isinstance(parsed, dict):
        return DiagramSpec.model_validate(parsed)

    text = _strip_fence(getattr(response, "text", "") or "")
    if not text:
        raise RuntimeError("Gemini returned no structured DiagramSpec.")
    return DiagramSpec.model_validate_json(text)


# =============================================================================
# GEMINI MODEL FALLBACK / RETRY
# =============================================================================

def _candidate_models(primary_model: str) -> list[str]:
    values: list[str] = []
    primary = (primary_model or "").strip()
    if primary:
        values.append(primary)

    fallback_text = os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.5-flash,gemini-3.1-flash-lite",
    )
    for raw in fallback_text.split(","):
        model = raw.strip()
        if model and model not in values:
            values.append(model)
    return values


def _retryable_error(error: Exception) -> bool:
    message = str(error).lower()
    markers = (
        "429",
        "resource_exhausted",
        "quota",
        "503",
        "unavailable",
        "high demand",
        "temporarily",
        "timeout",
        "deadline",
        "internal",
    )
    return any(marker in message for marker in markers)


def _generate_structured(
    client,
    model: str,
    system_prompt: str,
    contents,
):
    max_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "32768"))
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=DiagramSpec,
            temperature=0.0,
            max_output_tokens=max_tokens,
        ),
    )


def _call_models(
    client,
    primary_model: str,
    system_prompt: str,
    contents_factory,
) -> DiagramSpec:
    last_error: Exception | None = None

    for model in _candidate_models(primary_model):
        for attempt in range(2):
            try:
                response = _generate_structured(
                    client=client,
                    model=model,
                    system_prompt=system_prompt,
                    contents=contents_factory(attempt),
                )
                return _parse_diagram(response)
            except Exception as error:
                last_error = error
                text = str(error).lower()
                parse_problem = (
                    "validation" in text
                    or "json" in text
                    or "eof" in text
                    or "no structured" in text
                )
                if parse_problem and attempt == 0:
                    continue
                if not _retryable_error(error):
                    raise
                if (
                    attempt == 0
                    and (
                        "503" in text
                        or "unavailable" in text
                        or "high demand" in text
                    )
                ):
                    time.sleep(4)
                    continue
                break

    raise RuntimeError(
        "Gemini could not complete the topology analysis. "
        f"Last error: {last_error}"
    ) from last_error


# =============================================================================
# NODE / EDGE RECONCILIATION HELPERS
# =============================================================================

def _label_key(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _node_distance(a: DiagramNode, b: DiagramNode) -> float:
    return math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))


def _node_similarity(a: DiagramNode, b: DiagramNode) -> float:
    label_a = _label_key(a.label)
    label_b = _label_key(b.label)
    label_score = SequenceMatcher(None, label_a, label_b).ratio() if label_a and label_b else 0.0
    position_score = max(0.0, 1.0 - _node_distance(a, b) / 0.20)
    type_score = 1.0 if a.node_type == b.node_type else (0.55 if "other" in {a.node_type, b.node_type} else 0.0)
    return label_score * 0.55 + position_score * 0.35 + type_score * 0.10


def _unique_node_id(base_id: str, used: set[str]) -> str:
    root = _normalize_id(base_id) or "component"
    candidate = root
    suffix = 2
    while candidate in used:
        candidate = f"{root}_{suffix}"
        suffix += 1
    return candidate


def _candidate_node_match(
    candidate: DiagramNode,
    canonical_nodes: list[DiagramNode],
) -> DiagramNode | None:
    candidate_id = _normalize_id(candidate.id)
    for node in canonical_nodes:
        if _normalize_id(node.id) == candidate_id:
            return node

    candidate_label = _label_key(candidate.label)
    exact_label_matches = [node for node in canonical_nodes if _label_key(node.label) == candidate_label and candidate_label]
    if exact_label_matches:
        return min(exact_label_matches, key=lambda node: _node_distance(node, candidate))

    scored = sorted(
        ((_node_similarity(node, candidate), node) for node in canonical_nodes),
        key=lambda item: item[0],
        reverse=True,
    )
    if scored and scored[0][0] >= 0.68:
        return scored[0][1]
    return None


def _merge_candidate_with_locked_inventory(
    inventory: DiagramSpec,
    candidate: DiagramSpec,
) -> DiagramSpec:
    """
    Merge topology passes without allowing a later model response to delete edges.

    The old implementation replaced inventory.edges whenever the candidate returned
    any edges. In dense sketches that caused real pipes to disappear whenever the
    second model pass missed one. This version keeps the union and only deduplicates
    edges when their endpoints AND route geometry clearly describe the same pipe.
    """
    result = deepcopy(inventory)
    canonical_nodes = deepcopy(inventory.nodes)
    used_ids = {node.id for node in canonical_nodes}
    candidate_to_canonical: dict[str, str] = {}

    physical_canonical = [n for n in canonical_nodes if n.node_type != "junction"]
    junction_canonical = [n for n in canonical_nodes if n.node_type == "junction"]

    for candidate_node in candidate.nodes:
        raw_id = candidate_node.id
        if candidate_node.node_type == "junction":
            match = next(
                (j for j in junction_canonical if _node_distance(j, candidate_node) <= 0.035),
                None,
            )
            if match is None:
                match = deepcopy(candidate_node)
                match.id = _unique_node_id(match.id or "junction", used_ids)
                used_ids.add(match.id)
                canonical_nodes.append(match)
                junction_canonical.append(match)
            candidate_to_canonical[raw_id] = match.id
            candidate_to_canonical[_normalize_id(raw_id)] = match.id
            continue

        match = _candidate_node_match(candidate_node, physical_canonical)
        if match is None and float(candidate_node.confidence) >= 0.55:
            match = deepcopy(candidate_node)
            match.id = _unique_node_id(match.id or match.label, used_ids)
            used_ids.add(match.id)
            canonical_nodes.append(match)
            physical_canonical.append(match)
        if match is not None:
            if match.node_type == "other" and candidate_node.node_type != "other":
                match.node_type = candidate_node.node_type
            if len((candidate_node.label or '').strip()) > len((match.label or '').strip()):
                match.label = candidate_node.label
            candidate_to_canonical[raw_id] = match.id
            candidate_to_canonical[_normalize_id(raw_id)] = match.id

    for node in canonical_nodes:
        candidate_to_canonical.setdefault(node.id, node.id)
        candidate_to_canonical.setdefault(_normalize_id(node.id), node.id)
        candidate_to_canonical.setdefault(_label_key(node.label), node.id)

    remapped: list[DiagramEdge] = []
    for edge in candidate.edges:
        source = (
            candidate_to_canonical.get((edge.source or '').strip())
            or candidate_to_canonical.get(_normalize_id(edge.source))
            or candidate_to_canonical.get(_label_key(edge.source))
        )
        target = (
            candidate_to_canonical.get((edge.target or '').strip())
            or candidate_to_canonical.get(_normalize_id(edge.target))
            or candidate_to_canonical.get(_label_key(edge.target))
        )
        if source and target and source != target:
            copy_edge = deepcopy(edge)
            copy_edge.source = source
            copy_edge.target = target
            remapped.append(copy_edge)

    # Keep every inventory edge, then add candidate edges unless they are clearly
    # the same physical route. A route-rich edge wins over a route-poor duplicate.
    merged_edges = list(deepcopy(inventory.edges))

    def same_physical_pipe(a: DiagramEdge, b: DiagramEdge) -> bool:
        if {a.source, a.target} != {b.source, b.target}:
            return False
        if a.direction != b.direction and "unknown" not in {a.direction, b.direction}:
            return False
        # Two edges with the same endpoints are NOT automatically the same pipe.
        # Distinct side/anchor information is evidence of separate physical lines.
        if a.source_side != b.source_side or a.target_side != b.target_side:
            return False
        if a.source_anchor is not None and b.source_anchor is not None:
            if math.hypot(a.source_anchor.x - b.source_anchor.x, a.source_anchor.y - b.source_anchor.y) > 0.035:
                return False
        if a.target_anchor is not None and b.target_anchor is not None:
            if math.hypot(a.target_anchor.x - b.target_anchor.x, a.target_anchor.y - b.target_anchor.y) > 0.035:
                return False
        if a.waypoints and b.waypoints:
            return _route_distance(a, b) <= 0.055
        if not a.waypoints and not b.waypoints:
            return (a.pipe_size or '').strip().lower() == (b.pipe_size or '').strip().lower() and (a.label or '').strip().lower() == (b.label or '').strip().lower()
        return False

    for candidate_edge in remapped:
        match_index = next(
            (i for i, base_edge in enumerate(merged_edges) if same_physical_pipe(base_edge, candidate_edge)),
            None,
        )
        if match_index is None:
            candidate_edge.id = _unique_node_id(candidate_edge.id or "edge", {e.id for e in merged_edges})
            merged_edges.append(candidate_edge)
        else:
            # Prefer the edge containing more route geometry and better confidence.
            existing = merged_edges[match_index]
            if len(candidate_edge.waypoints) > len(existing.waypoints) or float(candidate_edge.confidence) > float(existing.confidence) + 0.08:
                keep_id = existing.id
                candidate_edge.id = keep_id
                merged_edges[match_index] = candidate_edge

    result.nodes = canonical_nodes
    result.edges = merged_edges
    result.title = inventory.title or candidate.title
    result.set_label = inventory.set_label or candidate.set_label
    result.summary = candidate.summary or inventory.summary
    result.warnings = list(dict.fromkeys([*inventory.warnings, *candidate.warnings]))
    result.style_notes = list(dict.fromkeys([*inventory.style_notes, *candidate.style_notes]))
    return result


# =============================================================================
# LIGHTWEIGHT OPENCV-IMAGE ROUTE SUPPORT CHECK
# =============================================================================

def _build_ink_mask(image):
    """Return a dark-stroke mask from the already enhanced image when numpy exists."""
    if np is None or image is None:
        return None
    try:
        gray = np.asarray(image.convert("L"))
        if gray.ndim != 2 or gray.size == 0:
            return None
        # Enhanced sketches are normally black-on-white. 190 keeps the traced
        # strokes while rejecting most page background.
        mask = gray < 190
        return mask
    except Exception:
        return None


def _boundary_anchor(node: DiagramNode, side: str | None) -> DiagramPoint:
    half_w = max(0.005, float(node.width) / 2)
    half_h = max(0.005, float(node.height) / 2)
    side = side or "right"
    if side == "left":
        return DiagramPoint(x=max(0.0, node.x - half_w), y=node.y)
    if side == "right":
        return DiagramPoint(x=min(1.0, node.x + half_w), y=node.y)
    if side == "top":
        return DiagramPoint(x=node.x, y=max(0.0, node.y - half_h))
    return DiagramPoint(x=node.x, y=min(1.0, node.y + half_h))


def _edge_trace_points(edge: DiagramEdge, lookup: dict[str, DiagramNode]) -> list[DiagramPoint]:
    source = lookup.get(edge.source)
    target = lookup.get(edge.target)
    if source is None or target is None:
        return []
    start = edge.source_anchor or _boundary_anchor(source, edge.source_side)
    end = edge.target_anchor or _boundary_anchor(target, edge.target_side)
    return [start, *edge.waypoints, end]


def _edge_image_support(
    edge: DiagramEdge,
    lookup: dict[str, DiagramNode],
    ink_mask,
) -> float:
    """
    Estimate whether the enhanced image contains dark stroke evidence near the
    proposed route. This is used only as a safeguard when two AI passes disagree;
    it never invents a connection by itself.
    """
    if ink_mask is None:
        return 0.5

    points = _edge_trace_points(edge, lookup)
    if len(points) < 2:
        return 0.0

    height, width = ink_mask.shape
    radius = max(3, int(min(width, height) * 0.0055))
    hits = 0
    samples = 0

    for a, b in zip(points, points[1:]):
        distance = math.hypot(float(b.x) - float(a.x), float(b.y) - float(a.y))
        count = max(8, min(70, int(distance * 120)))
        for index in range(count + 1):
            t = index / count
            x = float(a.x) + (float(b.x) - float(a.x)) * t
            y = float(a.y) + (float(b.y) - float(a.y)) * t
            px = min(width - 1, max(0, int(round(x * (width - 1)))))
            py = min(height - 1, max(0, int(round(y * (height - 1)))))
            x0 = max(0, px - radius)
            x1 = min(width, px + radius + 1)
            y0 = max(0, py - radius)
            y1 = min(height, py + radius + 1)
            patch = ink_mask[y0:y1, x0:x1]
            if patch.size and bool(patch.any()):
                hits += 1
            samples += 1

    return hits / samples if samples else 0.0


def _same_endpoint_pair(a: DiagramEdge, b: DiagramEdge) -> bool:
    return {a.source, a.target} == {b.source, b.target}


def _route_distance(a: DiagramEdge, b: DiagramEdge) -> float:
    if not a.waypoints or not b.waypoints:
        return 0.5
    count = min(len(a.waypoints), len(b.waypoints))
    if count <= 0:
        return 0.5
    total = 0.0
    for index in range(count):
        ia = round(index * (len(a.waypoints) - 1) / max(1, count - 1))
        ib = round(index * (len(b.waypoints) - 1) / max(1, count - 1))
        pa = a.waypoints[ia]
        pb = b.waypoints[ib]
        total += math.hypot(pa.x - pb.x, pa.y - pb.y)
    return total / count + abs(len(a.waypoints) - len(b.waypoints)) * 0.025


def _reconcile_topology_passes(
    base: DiagramSpec,
    candidate: DiagramSpec,
    enhanced_image,
) -> DiagramSpec:
    """
    Prefer the dedicated/audited candidate topology, but preserve a base edge that
    the later pass accidentally omitted when the enhanced image strongly supports
    the base route. This prevents the recurring "connection disappeared" failure.
    """
    merged = repair_diagram(_merge_candidate_with_locked_inventory(base, candidate))
    if not merged.edges:
        return repair_diagram(base)

    base_repaired = repair_diagram(base)
    base_count = len(base_repaired.edges)
    candidate_count = len(merged.edges)

    # Reject obviously collapsed/exploded audit results.
    if base_count >= 4 and candidate_count < max(2, int(base_count * 0.45)):
        return base_repaired
    if base_count >= 4 and candidate_count > max(base_count * 2.6, base_count + 16):
        return base_repaired

    ink_mask = _build_ink_mask(enhanced_image)
    lookup = {node.id: node for node in merged.nodes}
    result_edges = list(deepcopy(merged.edges))
    used_candidate: set[int] = set()

    for base_edge in base_repaired.edges:
        best_index = None
        best_distance = float("inf")
        for index, candidate_edge in enumerate(result_edges):
            if index in used_candidate or not _same_endpoint_pair(base_edge, candidate_edge):
                continue
            distance = _route_distance(base_edge, candidate_edge)
            if distance < best_distance:
                best_distance = distance
                best_index = index

        # Same physical endpoint pair is represented. Mark one candidate as its
        # counterpart so true parallel pipes can still be counted independently.
        if best_index is not None and best_distance <= 0.24:
            used_candidate.add(best_index)
            continue

        support = _edge_image_support(base_edge, lookup, ink_mask)
        preserve = False
        if base_edge.waypoints:
            preserve = support >= 0.54 and float(base_edge.confidence) >= 0.52
        else:
            preserve = support >= 0.68 and float(base_edge.confidence) >= 0.82

        if preserve:
            recovered = deepcopy(base_edge)
            recovered.id = f"{recovered.id}_recovered"
            result_edges.append(recovered)

    merged.edges = result_edges
    return repair_diagram(merged)


def _node_manifest(diagram: DiagramSpec) -> str:
    compact = DiagramSpec(
        title=diagram.title,
        set_label=diagram.set_label,
        summary=diagram.summary,
        nodes=diagram.nodes,
        edges=[],
        warnings=[],
        style_notes=[],
    )
    return compact.model_dump_json(indent=2)


# =============================================================================
# EXTRACTION
# =============================================================================

def analyze_sketch(
    client,
    model: str,
    original_image,
    enhanced_image,
) -> DiagramSpec:
    original_part = _image_to_part(original_image)
    enhanced_part = _image_to_part(enhanced_image)

    def inventory_contents(attempt: int):
        prompt = RETRY_PROMPT if attempt else (
            "Inventory every component and trace every visible pipeline before returning. "
            "Do not infer topology from engineering expectations."
        )
        return [prompt, original_part, enhanced_part]

    preliminary = repair_diagram(_call_models(
        client=client,
        primary_model=model,
        system_prompt=INVENTORY_AGENT_PROMPT,
        contents_factory=inventory_contents,
    ))

    manifest = _node_manifest(preliminary)

    def topology_contents(attempt: int):
        return [
            ("Repeat the endpoint-by-endpoint trace and recover EVERY line, including "
             "lines hidden in dense areas or close to other lines." if attempt else
             "Trace every physical pipeline independently using the locked component manifest.")
            + "\n\nLOCKED COMPONENT MANIFEST:\n" + manifest,
            original_part,
            enhanced_part,
        ]

    repaired = preliminary
    try:
        traced = _call_models(
            client=client,
            primary_model=model,
            system_prompt=TOPOLOGY_TRACE_PROMPT,
            contents_factory=topology_contents,
        )
        repaired = _reconcile_topology_passes(repaired, traced, enhanced_image)
    except Exception:
        pass

    # Mandatory connection-recall pass. This is deliberately independent from the
    # semantic/topology pass so a missed pipe can be added instead of lost.
    census_json = repaired.model_dump_json(indent=2)
    def census_contents(attempt: int):
        return [
            ("Audit every component side again. Find missing pipes only; never remove "
             "candidate edges. Repeat the full side-by-side census." if attempt else
             "Perform a strict connection census against the candidate." )
            + "\n\nLOCKED COMPONENT MANIFEST:\n" + manifest
            + "\n\nCURRENT CANDIDATE:\n" + census_json,
            original_part,
            enhanced_part,
        ]
    try:
        census = _call_models(
            client=client,
            primary_model=model,
            system_prompt=CONNECTION_CENSUS_PROMPT,
            contents_factory=census_contents,
        )
        repaired = _reconcile_topology_passes(repaired, census, enhanced_image)
    except Exception:
        pass

    # Final visual audit. The merge function is union-preserving, so this pass can
    # correct route details without deleting already recovered connections.
    candidate_json = repaired.model_dump_json(indent=2)
    def verify_contents(attempt: int):
        return [
            ("Audit every returned edge against BOTH images. Pay special attention to "
             "central manifolds, long outer routes, crossings, and parallel pipes. "
             "Do not delete an edge unless the image proves it is false." if not attempt else
             "Repeat the audit line-by-line and preserve every image-supported edge.")
            + "\n\nCANDIDATE DIAGRAMSPEC:\n" + candidate_json,
            original_part,
            enhanced_part,
        ]
    try:
        verified = _call_models(
            client=client,
            primary_model=model,
            system_prompt=VERIFY_AGENT_PROMPT,
            contents_factory=verify_contents,
        )
        repaired = _reconcile_topology_passes(repaired, verified, enhanced_image)
    except Exception:
        pass

    return repair_diagram(repaired)


# =============================================================================
# COMPLEX-DIAGRAM VERIFICATION
# =============================================================================

def _verification_mode() -> str:
    return os.getenv("GEMINI_TOPOLOGY_VERIFY", "auto").strip().lower()


def _needs_verification(diagram: DiagramSpec) -> bool:
    mode = _verification_mode()
    if mode in {"0", "false", "off", "no"}:
        return False
    if mode in {"1", "true", "on", "yes", "always"}:
        return True

    # Auto: verify diagrams where a single trace is most likely to lose lines.
    if len(diagram.nodes) >= 9:
        return True
    if len(diagram.edges) >= 9:
        return True
    if diagram.warnings:
        return True
    if any(node.confidence < 0.72 for node in diagram.nodes):
        return True
    if any(edge.confidence < 0.72 for edge in diagram.edges):
        return True
    if any(len(edge.waypoints) >= 5 for edge in diagram.edges):
        return True
    return False


def review_diagram(
    client,
    model: str,
    diagram: DiagramSpec,
) -> DiagramSpec:
    """
    Backward-compatible deterministic review used by app.py.

    The image-based audits are already performed inside analyze_sketch(), where
    the original and enhanced images are still available. This function therefore
    must not invent or redesign connections after the image evidence is gone.
    """
    return repair_diagram(diagram)


# =============================================================================
# DETERMINISTIC GRAPH REPAIR
# =============================================================================

def _numeric_suffix(*values: str) -> str:
    for value in values:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        if digits:
            return digits
    return ""


def _expand_component_label(label: str, node_type: str, node_id: str) -> str:
    clean = " ".join(str(label or "").replace("_", " ").split())
    if not clean:
        clean = str(node_id or "").replace("_", " ").strip()

    upper = clean.upper().replace(".", "")
    digits = _numeric_suffix(clean, node_id)

    if node_type == "motor":
        if upper in {"M", "MOTOR", "PUMP"}:
            return f"Motor {digits}".strip()
        if upper.startswith("M") and upper[1:].isdigit():
            return f"Motor {upper[1:]}"
        if upper.startswith("MOTOR"):
            suffix = _numeric_suffix(upper[5:], digits)
            return f"Motor {suffix}".strip() if suffix else "Motor"

    if "OHT" in upper:
        words: list[str] = []
        for word in clean.replace(".", "").split():
            if word.upper() == "OHT":
                # Avoid results such as "Tank Overhead Tank" or duplicated
                # "Overhead Tank Overhead Tank".
                if (
                    len(words) >= 2
                    and words[-2].lower() == "overhead"
                    and words[-1].lower() == "tank"
                ):
                    continue
                if words and words[-1].lower() == "tank":
                    words.pop()
                words.extend(["Overhead", "Tank"])
            else:
                words.append(word.title() if word.isupper() else word)
        return " ".join(words).strip()

    return clean.title() if clean.isupper() else clean


def _normalize_id(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace(" ", "_").replace("-", "_").replace("/", "_")
    value = "".join(character for character in value if character.isalnum() or character == "_")
    return "_".join(part for part in value.split("_") if part)


def _clean_point(point: DiagramPoint | None) -> DiagramPoint | None:
    if point is None:
        return None
    return DiagramPoint(
        x=min(max(float(point.x), 0.0), 1.0),
        y=min(max(float(point.y), 0.0), 1.0),
    )


def _clean_waypoints(points: list[DiagramPoint]) -> list[DiagramPoint]:
    """Keep ordered route geometry; only remove near-identical consecutive points."""
    cleaned: list[DiagramPoint] = []
    for point in points:
        candidate = _clean_point(point)
        if candidate is None:
            continue
        if cleaned:
            previous = cleaned[-1]
            if abs(previous.x - candidate.x) < 0.002 and abs(previous.y - candidate.y) < 0.002:
                continue
        cleaned.append(candidate)
    # Do not downsample real bends. Large diagrams may legitimately need many.
    return cleaned[:32]


def _side_from_vector(dx: float, dy: float) -> str:
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0 else "left"
    return "bottom" if dy >= 0 else "top"


def _infer_sides(edge: DiagramEdge, lookup: dict[str, DiagramNode]) -> None:
    source = lookup.get(edge.source)
    target = lookup.get(edge.target)
    if source is None or target is None:
        return

    if edge.source_side is None:
        if edge.source_anchor is not None:
            edge.source_side = _side_from_vector(
                edge.source_anchor.x - source.x,
                edge.source_anchor.y - source.y,
            )
        elif edge.waypoints:
            first = edge.waypoints[0]
            edge.source_side = _side_from_vector(first.x - source.x, first.y - source.y)
        else:
            edge.source_side = _side_from_vector(target.x - source.x, target.y - source.y)

    if edge.target_side is None:
        if edge.target_anchor is not None:
            edge.target_side = _side_from_vector(
                edge.target_anchor.x - target.x,
                edge.target_anchor.y - target.y,
            )
        elif edge.waypoints:
            last = edge.waypoints[-1]
            edge.target_side = _side_from_vector(last.x - target.x, last.y - target.y)
        else:
            edge.target_side = _side_from_vector(source.x - target.x, source.y - target.y)


def _derive_route_hint(edge: DiagramEdge, lookup: dict[str, DiagramNode]) -> None:
    if edge.route_hint != "auto":
        return

    source = lookup.get(edge.source)
    target = lookup.get(edge.target)
    if source is None or target is None or not edge.waypoints:
        edge.route_hint = "direct"
        return

    min_x = min(point.x for point in edge.waypoints)
    max_x = max(point.x for point in edge.waypoints)
    min_y = min(point.y for point in edge.waypoints)
    max_y = max(point.y for point in edge.waypoints)

    node_min_x = min(source.x, target.x)
    node_max_x = max(source.x, target.x)
    node_min_y = min(source.y, target.y)
    node_max_y = max(source.y, target.y)
    margin = 0.12

    if min_y < node_min_y - margin:
        edge.route_hint = "top_outer"
    elif max_y > node_max_y + margin:
        edge.route_hint = "bottom_outer"
    elif min_x < node_min_x - margin:
        edge.route_hint = "left_outer"
    elif max_x > node_max_x + margin:
        edge.route_hint = "right_outer"
    else:
        edge.route_hint = "direct"


def repair_diagram(diagram: DiagramSpec) -> DiagramSpec:
    """
    Deterministic sanitation that MUST NOT redesign the engineering graph.

    It only normalizes ids/text/coordinates, repairs endpoint references, keeps all
    valid physical edges (including parallel pipes), preserves direction, anchors,
    ordered waypoints, and infers missing sides from image-derived geometry.
    """
    result = deepcopy(diagram)

    nodes: list[DiagramNode] = []
    seen_ids: set[str] = set()
    id_map: dict[str, str] = {}
    label_map: dict[str, str] = {}

    for index, node in enumerate(result.nodes, start=1):
        raw_id = (node.id or "").strip()
        base_id = _normalize_id(raw_id) or f"component_{index}"
        final_id = _unique_node_id(base_id, seen_ids)

        if raw_id:
            id_map.setdefault(raw_id, final_id)
            id_map.setdefault(raw_id.lower(), final_id)
        id_map.setdefault(base_id, final_id)
        id_map.setdefault(_normalize_id(base_id), final_id)

        raw_label = " ".join((node.label or "").split())
        node.id = final_id
        node.label = _expand_component_label(
            raw_label or final_id.replace("_", " ").title(),
            node.node_type,
            final_id,
        )[:120]
        node.x = min(max(float(node.x), 0.001), 0.999)
        node.y = min(max(float(node.y), 0.001), 0.999)
        node.width = min(max(float(node.width), 0.01), 0.50)
        node.height = min(max(float(node.height), 0.01), 0.50)
        node.details = [
            " ".join(str(detail).split())[:120]
            for detail in node.details[:5]
            if str(detail).strip()
        ]

        seen_ids.add(final_id)
        nodes.append(node)
        if raw_label:
            label_map.setdefault(_label_key(raw_label), final_id)
            label_map.setdefault(_normalize_id(raw_label), final_id)
        label_map.setdefault(_label_key(node.label), final_id)
        label_map.setdefault(_normalize_id(node.label), final_id)

    result.nodes = nodes
    valid_ids = {node.id for node in result.nodes}

    edges: list[DiagramEdge] = []
    seen_edge_ids: set[str] = set()

    def resolve_endpoint(raw: str) -> str:
        raw = (raw or "").strip()
        return (
            id_map.get(raw)
            or id_map.get(raw.lower())
            or id_map.get(_normalize_id(raw))
            or label_map.get(_label_key(raw))
            or label_map.get(_normalize_id(raw))
            or _normalize_id(raw)
        )

    for index, edge in enumerate(result.edges, start=1):
        source = resolve_endpoint(edge.source)
        target = resolve_endpoint(edge.target)
        if source not in valid_ids or target not in valid_ids or source == target:
            continue

        edge.source = source
        edge.target = target
        edge_id = _normalize_id(edge.id) or f"edge_{index}"
        edge.id = _unique_node_id(edge_id, seen_edge_ids)
        seen_edge_ids.add(edge.id)
        edge.label = " ".join((edge.label or "").split())[:140]
        edge.pipe_size = " ".join((edge.pipe_size or "").split())[:60]
        edge.source_anchor = _clean_point(edge.source_anchor)
        edge.target_anchor = _clean_point(edge.target_anchor)
        edge.waypoints = _clean_waypoints(edge.waypoints)
        edge.locked_route = True
        edges.append(edge)

    result.edges = edges
    lookup = {node.id: node for node in result.nodes}
    for edge in result.edges:
        _infer_sides(edge, lookup)
        _derive_route_hint(edge, lookup)

    clean_warnings: list[str] = []
    seen_warnings: set[str] = set()
    for warning in result.warnings:
        clean = " ".join(str(warning).split())[:300]
        if not clean:
            continue
        key = clean.lower()
        if key in seen_warnings:
            continue
        seen_warnings.add(key)
        clean_warnings.append(clean)
    result.warnings = clean_warnings
    return result