from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai

from src.ai_pipeline import analyze_sketch, review_diagram
from src.component_catalog import (
    COMPONENT_CATALOG,
    build_selected_component_diagram,
)
from src.image_utils import enhance_sketch, load_image, resize_for_ai, rotate_image
from src.renderers import (
    component_asset_path,
    create_powerpoint,
    create_preview_png,
    node_component_asset_path,
    png_to_pdf,
)


# =============================================================================
# ENVIRONMENT / PATHS
# =============================================================================

load_dotenv()
ROOT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets" / "components"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_COMPONENT_ASSETS = {
    "sump": {
        "display_name": "Sump Tank",
        "expected_names": "sump_real.png / sump_real.jpg / sump_real.jpeg",
    },
    "bore": {
        "display_name": "Bore",
        "expected_names": "bore_real.png / bore_real.jpg / bore_real.jpeg",
    },
    "oht": {
        "display_name": "OHT Tank",
        "expected_names": "tank_real.png / tank_real.jpg / tank_real.jpeg",
    },
    "motor": {
        "display_name": "Motor (Pump)",
        "expected_names": "motor_real.png / motor_real.jpg / motor_real.jpeg",
    },
}


# =============================================================================
# PAGE CONFIG / PREMIUM REFERENCE THEME
# =============================================================================

st.set_page_config(
    page_title="Agentic Sketch-to-PPT",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
:root {
    --navy: #073c78;
    --navy2: #0756a4;
    --blue: #0a66e3;
    --blue2: #006cf0;
    --pale: #f4f9ff;
    --line: #d8e6f7;
    --text: #0b2f67;
    --muted: #5f7391;
    --green: #16a564;
}

html, body, [class*="css"] { font-family: Inter, "Segoe UI", Arial, sans-serif; }
.stApp { background: linear-gradient(180deg, #eef7ff 0%, #f9fcff 38%, #ffffff 100%); }
.block-container { max-width: 1760px; padding: 0 14px 22px 14px; }
header[data-testid="stHeader"] { background: transparent; }

.premium-header {
    margin: 0 -14px 14px -14px;
    padding: 14px 28px;
    background: linear-gradient(110deg, #06346d 0%, #075398 56%, #065bad 100%);
    color: white;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 6px 18px rgba(4, 57, 115, 0.18);
}
.brand-wrap { display:flex; gap:14px; align-items:center; }
.brand-icon {
    width:58px; height:58px; border-radius:18px;
    display:flex; align-items:center; justify-content:center;
    font-size:35px; background:rgba(255,255,255,.10);
    border:1px solid rgba(255,255,255,.18);
}
.brand-title { font-size:26px; font-weight:800; line-height:1.05; }
.brand-subtitle { margin-top:5px; font-size:14px; opacity:.94; }
.steps { display:flex; gap:20px; align-items:center; white-space:nowrap; }
.step { display:flex; align-items:center; gap:9px; font-weight:650; font-size:14px; }
.step-dot {
    width:36px; height:36px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    background:#0a66e3; border:1px solid rgba(255,255,255,.65); box-shadow:inset 0 0 0 1px rgba(0,0,0,.05);
}
.step-dot.active { background:#12b85d; }
.step-arrow { font-size:22px; opacity:.85; }

.panel-title { color:#053a8f; font-size:19px; font-weight:800; margin-bottom:8px; }
.success-pill {
    display:inline-flex; align-items:center; gap:8px; background:#eaf8f0; color:#17834f;
    border:1px solid #c8ecd7; border-radius:18px; padding:7px 12px; font-weight:700; font-size:12px;
}
.mini-note { color:#647a99; font-size:12px; }
.catalog-group {
    background:#f7fbff; border:1px solid #dbe9f8; border-radius:10px;
    padding:9px 11px; margin:6px 0; color:#173f75; font-size:12px;
}
.catalog-group b { color:#073a8c; }

[data-testid="stFileUploader"] section {
    border:1.5px dashed #8ebff8 !important;
    background:linear-gradient(180deg,#f8fbff,#f2f8ff) !important;
    border-radius:12px !important;
    min-height:160px;
}
[data-testid="stFileUploader"] section:hover { border-color:#0a66e3 !important; }
.stButton > button, .stDownloadButton > button {
    border-radius:9px !important; min-height:44px; font-weight:750 !important;
    border:1px solid #0a66e3 !important;
}
.stDownloadButton > button[kind="primary"], .stButton > button[kind="primary"] {
    background:linear-gradient(135deg,#0872ef,#0759cc) !important;
    color:white !important;
}
[data-testid="stImage"] img { border-radius:9px; }
[data-testid="stDataFrame"] { border:1px solid #dbe8f7; border-radius:10px; overflow:hidden; }
hr { border-color:#dbe8f7 !important; }
.footer-bar {
    margin: 18px -14px -22px -14px; background:#063873; color:white; padding:12px 28px;
    display:flex; justify-content:space-between; font-size:12px;
}
@media (max-width: 1100px) {
    .steps { display:none; }
    .brand-title { font-size:21px; }
}
</style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# HELPERS
# =============================================================================

def reset_outputs() -> None:
    for key in (
        "diagram",
        "preview_png",
        "pptx_bytes",
        "pdf_bytes",
        "processed_hash",
    ):
        st.session_state.pop(key, None)


def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
    return genai.Client(api_key=api_key)


def safe_confidence(value) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def get_component_asset_status() -> dict:
    status = {}
    for node_type, config in REQUIRED_COMPONENT_ASSETS.items():
        path = component_asset_path(ASSETS_DIR, node_type)
        status[node_type] = {
            "display_name": config["display_name"],
            "expected_names": config["expected_names"],
            "found": path is not None,
            "path": path,
        }
    return status


def missing_required_assets() -> list[dict]:
    return [item for item in get_component_asset_status().values() if not item["found"]]


def validate_required_assets() -> None:
    missing = missing_required_assets()
    if not missing:
        return
    lines = [f"{item['display_name']}: {item['expected_names']}" for item in missing]
    raise RuntimeError(
        "Required component images are missing.\n\n"
        f"Place these inside: {ASSETS_DIR}\n\n" + "\n".join(lines)
    )


def display_label(node) -> str:
    label = " ".join(str(getattr(node, "label", "") or "").split())
    return label or str(getattr(node, "id", "Component")).replace("_", " ").title()


def build_component_selection_df(selected_names: list[str] | None = None) -> pd.DataFrame:
    """Build the fixed component table used by the checkbox selector."""
    selected_set = set(selected_names or [])
    rows = []
    for index, item in enumerate(COMPONENT_CATALOG, start=1):
        rows.append(
            {
                "Select": item.name in selected_set,
                "#": index,
                "Component Type": item.group,
                "Component": item.name,
                "Code": item.code,
                "Details": item.connection_label,
            }
        )
    return pd.DataFrame(rows)


def asset_signature_for_hashing(root_dir: Path) -> str:
    """Return a stable signature that changes whenever component assets change.

    This fixes the old-image caching problem in component-selection mode: if the
    user replaces an image with a newer one but keeps the same component table
    selection, the generated output must still regenerate automatically.
    """
    if not root_dir.exists():
        return ""

    parts: list[str] = []
    for path in sorted(root_dir.rglob('*')):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            continue
        try:
            stat = path.stat()
            parts.append(f"{path.relative_to(root_dir)}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            continue
    return '|'.join(parts)


def render_outputs(diagram) -> None:
    """Use the existing renderer for PNG, PPT and PDF in both input modes."""
    preview_png = create_preview_png(diagram=diagram, assets_dir=ASSETS_DIR)
    pptx_bytes = create_powerpoint(diagram=diagram, assets_dir=ASSETS_DIR)
    pdf_bytes = png_to_pdf(preview_png)

    st.session_state["diagram"] = diagram
    st.session_state["preview_png"] = preview_png
    st.session_state["pptx_bytes"] = pptx_bytes
    st.session_state["pdf_bytes"] = pdf_bytes


# =============================================================================
# GENERATION PIPELINES
# =============================================================================

def generate_professional_diagram(uploaded_bytes: bytes, orientation: str) -> None:
    """Existing sketch → AI topology → professional diagram workflow."""
    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    validate_required_assets()

    with st.status("Processing sketch and generating professional diagram...", expanded=True) as status:
        st.write("1/5  Loading hand-drawn image")
        original = resize_for_ai(rotate_image(load_image(uploaded_bytes), orientation))

        st.write("2/5  Enhancing handwriting and pipeline geometry with OpenCV")
        enhanced = enhance_sketch(original)

        client = get_gemini_client()

        st.write("3/5  Sketch Understanding Agent extracting components and exact connections")
        extracted = analyze_sketch(
            client=client,
            model=model,
            original_image=original,
            enhanced_image=enhanced,
        )

        st.write("4/5  Engineering Review Agent validating topology and layout")
        reviewed = review_diagram(client=client, model=model, diagram=extracted)

        st.write("5/5  Rendering premium PNG, editable PowerPoint and PDF")
        render_outputs(reviewed)
        status.update(label="Diagram created successfully", state="complete", expanded=False)


def generate_selected_components(selected_components: list[str]) -> None:
    """New selection → auto-layout → auto-connections → existing renderer workflow."""
    diagram = build_selected_component_diagram(selected_components)
    render_outputs(diagram)


# =============================================================================
# HEADER
# =============================================================================

st.markdown(
    """
<div class="premium-header">
  <div class="brand-wrap">
    <div class="brand-icon">💧</div>
    <div>
      <div class="brand-title">Agentic Sketch-to-PPT</div>
      <div class="brand-subtitle">Convert Your Sketch to Professional Diagrams & PowerPoint</div>
    </div>
  </div>
  <div class="steps">
    <div class="step"><div class="step-dot active">1</div><span>Upload & Select</span></div>
    <div class="step-arrow">→</div>
    <div class="step"><div class="step-dot">2</div><span>Process & Configure</span></div>
    <div class="step-arrow">→</div>
    <div class="step"><div class="step-dot">3</div><span>Generate & Download</span></div>
  </div>
</div>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# MAIN WORKSPACE
# =============================================================================

uploaded_file = None
orientation = "Auto / No rotation"

# Keep table selections stable across Streamlit reruns.
if "selected_components" not in st.session_state:
    st.session_state["selected_components"] = []

left_col, center_col, right_col = st.columns([1.05, 1.28, 0.78], gap="small")

with left_col:
    # -------------------------------------------------------------------------
    # 1. Upload Sketch - existing workflow remains available.
    # -------------------------------------------------------------------------
    st.markdown('<div class="panel-title">1. Upload Your Sketch</div>', unsafe_allow_html=True)
    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "Drag & drop your sketch here or click to browse",
            type=["png", "jpg", "jpeg", "webp"],
            help=(
                "Optional. Upload one hand-drawn engineering diagram. "
                "When one or more components are checked below, the selected-component "
                "diagram takes priority and only those checked components are rendered."
            ),
        )
        orientation = st.selectbox(
            "Image orientation",
            ["Auto / No rotation", "90° clockwise", "90° counter-clockwise", "180°"],
            index=0,
        )
        if uploaded_file is None:
            st.caption("Upload a sketch to use the existing AI extraction workflow.")
        else:
            st.success("Sketch uploaded. You may also select components from the table below.")

    # -------------------------------------------------------------------------
    # 2. Select Components - ALWAYS visible directly below Upload Sketch.
    # -------------------------------------------------------------------------
    st.markdown('<div class="panel-title">2. Select Components (Table)</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.caption(
            "Check only the components required in the final diagram. "
            "The generated diagram updates automatically whenever the selection changes."
        )

        # Seed values are recreated from the last accepted selection. The data_editor
        # widget keeps its own edit state through reruns using the stable key below.
        component_table = build_component_selection_df(
            st.session_state.get("selected_components", [])
        )

        edited_table = st.data_editor(
            component_table,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key="component_selection_editor",
            column_config={
                "Select": st.column_config.CheckboxColumn(
                    "Select",
                    help="Include this component in the generated diagram",
                    default=False,
                    width="small",
                ),
                "#": st.column_config.NumberColumn("#", width="small"),
                "Component Type": st.column_config.TextColumn(
                    "Component Type", width="medium"
                ),
                "Component": st.column_config.TextColumn(
                    "Component", width="large"
                ),
                "Code": st.column_config.TextColumn("Code", width="small"),
                "Details": st.column_config.TextColumn(
                    "Connection", width="medium"
                ),
            },
            disabled=["#", "Component Type", "Component", "Code", "Details"],
        )

        selected_components = edited_table.loc[
            edited_table["Select"].fillna(False), "Component"
        ].tolist()
        st.session_state["selected_components"] = selected_components

        if selected_components:
            st.success(
                f"{len(selected_components)} component(s) selected. "
                "Only these components will appear in the generated diagram."
            )
        else:
            st.info(
                "No components selected. Check one or more rows to generate a "
                "component-based diagram."
            )

    # Preserve the existing component-image status without competing with the
    # reference-style selection table. It stays available as a collapsed section.
    with st.expander("Component / Rendering Setup", expanded=False):
        asset_status = get_component_asset_status()
        for _node_type, item in asset_status.items():
            c1, c2 = st.columns([0.30, 0.70])
            with c1:
                if item["found"]:
                    st.image(str(item["path"]), use_container_width=True)
                else:
                    st.markdown("❌")
            with c2:
                st.markdown(f"**{item['display_name']}**")
                st.caption(
                    item["path"].name if item["found"] else item["expected_names"]
                )

        missing = missing_required_assets()
        if missing:
            st.warning(
                "Some real assets required by the original sketch workflow are missing. "
                "Component-table generation can still use the built-in professional cards."
            )
        else:
            st.success("Existing real component assets are configured.")


# =============================================================================
# INPUT PROCESSING / AUTOMATIC GENERATION
# =============================================================================

uploaded_bytes = uploaded_file.getvalue() if uploaded_file is not None else None
source_image = None
opencv_image = None
selected_components = st.session_state.get("selected_components", [])

# Selected components have priority because the requirement is that ONLY checked
# table rows are rendered when the user makes a table selection. If the table is
# empty, the original sketch-analysis workflow remains unchanged.
if selected_components:
    selection_signature = "|".join(selected_components)
    asset_signature = asset_signature_for_hashing(ASSETS_DIR)
    current_hash = hashlib.sha256(
        f"selection|{selection_signature}|assets|{asset_signature}".encode("utf-8")
    ).hexdigest()

    if st.session_state.get("processed_hash") != current_hash:
        try:
            with st.spinner(
                "Automatically arranging and connecting selected components..."
            ):
                generate_selected_components(selected_components)
            st.session_state["processed_hash"] = current_hash
        except Exception as exc:
            st.error("Automatic component diagram generation failed.")
            st.exception(exc)

elif uploaded_bytes is not None:
    source_image = rotate_image(load_image(uploaded_bytes), orientation)
    opencv_image = enhance_sketch(resize_for_ai(source_image))

    signature_parts = []
    for item in get_component_asset_status().values():
        path = item["path"]
        if path is not None:
            signature_parts.append(f"{path.resolve()}:{path.stat().st_mtime_ns}")

    current_hash = hashlib.sha256(
        b"sketch|"
        + uploaded_bytes
        + orientation.encode("utf-8")
        + "|".join(sorted(signature_parts)).encode("utf-8")
    ).hexdigest()

    if (
        st.session_state.get("processed_hash") != current_hash
        and not missing_required_assets()
    ):
        try:
            generate_professional_diagram(uploaded_bytes, orientation)
            st.session_state["processed_hash"] = current_hash
        except Exception as exc:
            st.error("Diagram generation failed.")
            st.exception(exc)

else:
    # Nothing is selected and no sketch exists, therefore an earlier output should
    # not remain visible as if it still represented the current input state.
    if st.session_state.get("diagram") is not None:
        reset_outputs()


# =============================================================================
# GENERATED DIAGRAM
# =============================================================================

with center_col:
    title = "3. Generated Diagram"
    if st.session_state.get("diagram") is not None:
        diagram = st.session_state["diagram"]
        visible_count = sum(
            1
            for node in diagram.nodes
            if getattr(node, "node_type", "") != "junction"
        )
        title = (
            f"3. Generated Diagram "
            f"({visible_count} components / {len(diagram.edges)} connections)"
        )

    st.markdown(f'<div class="panel-title">{title}</div>', unsafe_allow_html=True)

    with st.container(border=True):
        if st.session_state.get("preview_png") is not None:
            pill_col, _ = st.columns([0.45, 0.55])
            with pill_col:
                st.markdown(
                    '<span class="success-pill">✓ Diagram Created Successfully</span>',
                    unsafe_allow_html=True,
                )
            st.image(st.session_state["preview_png"], use_container_width=True)

        elif source_image is not None:
            tab1, tab2 = st.tabs(["Uploaded Sketch", "OpenCV Enhanced"])
            with tab1:
                st.image(source_image, use_container_width=True)
            with tab2:
                st.image(opencv_image, use_container_width=True)
            st.caption("The professional diagram will appear here after processing.")

        else:
            st.markdown(
                """
                <div style="min-height:640px;display:flex;align-items:center;
                            justify-content:center;text-align:center;color:#6d83a2;">
                    <div>
                        <div style="font-size:66px">⬆️</div>
                        <b>Upload a sketch or select components from the table.</b><br>
                        <span style="font-size:13px">
                            When components are checked, only those checked components
                            are automatically arranged, connected and rendered.
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# =============================================================================
# DETAILS / EXPORTS
# =============================================================================

with right_col:
    st.markdown('<div class="panel-title">4. Output / Component Details</div>', unsafe_allow_html=True)

    diagram = st.session_state.get("diagram")
    if diagram is None:
        with st.container(border=True):
            st.info("Component details and export options will appear here after generation.")
    else:
        for node in diagram.nodes:
            if getattr(node, "node_type", "") == "junction":
                continue
            with st.container(border=True):
                img_col, detail_col = st.columns([0.36, 0.64])
                with img_col:
                    asset = node_component_asset_path(ASSETS_DIR, node)
                    if asset is not None:
                        st.image(str(asset), use_container_width=True)
                    else:
                        code = next(
                            (
                                str(detail).split(":", 1)[1].strip()
                                for detail in getattr(node, "details", []) or []
                                if str(detail).lower().startswith("code:")
                            ),
                            getattr(node, "node_type", "COMP").upper(),
                        )
                        st.markdown(
                            f"<div style='height:72px;border:1px solid #bcd7f5;border-radius:10px;background:#eef7ff;display:flex;align-items:center;justify-content:center;color:#073c78;font-weight:800;font-size:18px'>{code}</div>",
                            unsafe_allow_html=True,
                        )
                with detail_col:
                    st.markdown(f"**{display_label(node)}**")
                    st.caption(f"Type: {getattr(node, 'node_type', 'other').title()}")
                    details = list(getattr(node, "details", []) or [])[:4]
                    for detail in details:
                        st.markdown(f"<span class='mini-note'>• {detail}</span>", unsafe_allow_html=True)
                    st.caption(f"Confidence: {safe_confidence(getattr(node, 'confidence', 0))}")

        with st.container(border=True):
            st.markdown("**Connection Summary**")
            rows = []
            nodes_by_id = {node.id: display_label(node) for node in diagram.nodes}
            for edge in diagram.edges:
                rows.append(
                    {
                        "From": nodes_by_id.get(edge.source, edge.source),
                        "To": nodes_by_id.get(edge.target, edge.target),
                        "Connection": edge.label or edge.pipe_size or "—",
                    }
                )
            if rows:
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                    height=min(330, 38 + 34 * max(1, len(rows))),
                )
            else:
                st.caption("No connections are required for a single selected component.")

        with st.container(border=True):
            st.markdown("**Export Options**")
            st.download_button(
                "⬇ Download Image (PNG)",
                st.session_state["preview_png"],
                "professional_site_diagram.png",
                "image/png",
                use_container_width=True,
            )
            st.download_button(
                "⬇ Download PPT (PowerPoint)",
                st.session_state["pptx_bytes"],
                "professional_site_diagram.pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )
            st.download_button(
                "⬇ Download PDF",
                st.session_state["pdf_bytes"],
                "professional_site_diagram.pdf",
                "application/pdf",
                use_container_width=True,
            )


# =============================================================================
# EXISTING ENGINEERING DETAILS / DEBUG OUTPUT
# =============================================================================

if st.session_state.get("diagram") is not None:
    diagram = st.session_state["diagram"]
    with st.expander("AI interpretation details / engineering JSON"):
        component_rows = [
            {
                "Name": display_label(node),
                "Type": node.node_type,
                "Confidence": safe_confidence(getattr(node, "confidence", 0)),
                "Details": ", ".join(getattr(node, "details", []) or []),
            }
            for node in diagram.nodes
        ]
        st.markdown("#### Components")
        st.dataframe(pd.DataFrame(component_rows), use_container_width=True, hide_index=True)

        connection_rows = [
            {
                "From": edge.source,
                "To": edge.target,
                "Pipe Size": edge.pipe_size,
                "Label": edge.label,
                "Confidence": safe_confidence(getattr(edge, "confidence", 0)),
            }
            for edge in diagram.edges
        ]
        st.markdown("#### Connections")
        st.dataframe(pd.DataFrame(connection_rows), use_container_width=True, hide_index=True)

        if diagram.warnings:
            st.markdown("#### AI warnings")
            for warning in diagram.warnings:
                st.warning(warning)
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai

from src.ai_pipeline import analyze_sketch, review_diagram
from src.component_catalog import (
    COMPONENT_CATALOG,
    build_selected_component_diagram,
)
from src.image_utils import enhance_sketch, load_image, resize_for_ai, rotate_image
from src.renderers import (
    component_asset_path,
    create_powerpoint,
    create_preview_png,
    node_component_asset_path,
    png_to_pdf,
)


# =============================================================================
# ENVIRONMENT / PATHS
# =============================================================================

load_dotenv()
ROOT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets" / "components"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_COMPONENT_ASSETS = {
    "sump": {
        "display_name": "Sump Tank",
        "expected_names": "sump_reference.png / sump_real.png / sump_real.jpg / sump_real.jpeg",
    },
    "bore": {
        "display_name": "Bore",
        "expected_names": "bore_reference.png / bore_real.png / bore_real.jpg / bore_real.jpeg",
    },
    "oht": {
        "display_name": "OHT Tank",
        "expected_names": "oht_reference.png / tank_real.png / tank_real.jpg / tank_real.jpeg",
    },
    "motor": {
        "display_name": "Motor (Pump)",
        "expected_names": "motor_reference.png / motor_real.png / motor_real.jpg / motor_real.jpeg",
    },
}


# =============================================================================
# PAGE CONFIG / PREMIUM REFERENCE THEME
# =============================================================================

st.set_page_config(
    page_title="Agentic Sketch-to-PPT",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
:root {
    --navy: #073c78;
    --navy2: #0756a4;
    --blue: #0a66e3;
    --blue2: #006cf0;
    --pale: #f4f9ff;
    --line: #d8e6f7;
    --text: #0b2f67;
    --muted: #5f7391;
    --green: #16a564;
}

html, body, [class*="css"] { font-family: Inter, "Segoe UI", Arial, sans-serif; }
.stApp { background: linear-gradient(180deg, #eef7ff 0%, #f9fcff 38%, #ffffff 100%); }
.block-container { max-width: 1760px; padding: 0 14px 22px 14px; }
header[data-testid="stHeader"] { background: transparent; }

.premium-header {
    margin: 0 -14px 14px -14px;
    padding: 14px 28px;
    background: linear-gradient(110deg, #06346d 0%, #075398 56%, #065bad 100%);
    color: white;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 6px 18px rgba(4, 57, 115, 0.18);
}
.brand-wrap { display:flex; gap:14px; align-items:center; }
.brand-icon {
    width:58px; height:58px; border-radius:18px;
    display:flex; align-items:center; justify-content:center;
    font-size:35px; background:rgba(255,255,255,.10);
    border:1px solid rgba(255,255,255,.18);
}
.brand-title { font-size:26px; font-weight:800; line-height:1.05; }
.brand-subtitle { margin-top:5px; font-size:14px; opacity:.94; }
.steps { display:flex; gap:20px; align-items:center; white-space:nowrap; }
.step { display:flex; align-items:center; gap:9px; font-weight:650; font-size:14px; }
.step-dot {
    width:36px; height:36px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    background:#0a66e3; border:1px solid rgba(255,255,255,.65); box-shadow:inset 0 0 0 1px rgba(0,0,0,.05);
}
.step-dot.active { background:#12b85d; }
.step-arrow { font-size:22px; opacity:.85; }

.panel-title { color:#053a8f; font-size:19px; font-weight:800; margin-bottom:8px; }
.success-pill {
    display:inline-flex; align-items:center; gap:8px; background:#eaf8f0; color:#17834f;
    border:1px solid #c8ecd7; border-radius:18px; padding:7px 12px; font-weight:700; font-size:12px;
}
.mini-note { color:#647a99; font-size:12px; }
.catalog-group {
    background:#f7fbff; border:1px solid #dbe9f8; border-radius:10px;
    padding:9px 11px; margin:6px 0; color:#173f75; font-size:12px;
}
.catalog-group b { color:#073a8c; }

[data-testid="stFileUploader"] section {
    border:1.5px dashed #8ebff8 !important;
    background:linear-gradient(180deg,#f8fbff,#f2f8ff) !important;
    border-radius:12px !important;
    min-height:160px;
}
[data-testid="stFileUploader"] section:hover { border-color:#0a66e3 !important; }
.stButton > button, .stDownloadButton > button {
    border-radius:9px !important; min-height:44px; font-weight:750 !important;
    border:1px solid #0a66e3 !important;
}
.stDownloadButton > button[kind="primary"], .stButton > button[kind="primary"] {
    background:linear-gradient(135deg,#0872ef,#0759cc) !important;
    color:white !important;
}
[data-testid="stImage"] img { border-radius:9px; }
[data-testid="stDataFrame"] { border:1px solid #dbe8f7; border-radius:10px; overflow:hidden; }
hr { border-color:#dbe8f7 !important; }
.footer-bar {
    margin: 18px -14px -22px -14px; background:#063873; color:white; padding:12px 28px;
    display:flex; justify-content:space-between; font-size:12px;
}
@media (max-width: 1100px) {
    .steps { display:none; }
    .brand-title { font-size:21px; }
}
</style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# HELPERS
# =============================================================================

def reset_outputs() -> None:
    for key in (
        "diagram",
        "preview_png",
        "pptx_bytes",
        "pdf_bytes",
        "processed_hash",
    ):
        st.session_state.pop(key, None)


def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
    return genai.Client(api_key=api_key)


def safe_confidence(value) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def get_component_asset_status() -> dict:
    status = {}
    for node_type, config in REQUIRED_COMPONENT_ASSETS.items():
        path = component_asset_path(ASSETS_DIR, node_type)
        status[node_type] = {
            "display_name": config["display_name"],
            "expected_names": config["expected_names"],
            "found": path is not None,
            "path": path,
        }
    return status


def missing_required_assets() -> list[dict]:
    return [item for item in get_component_asset_status().values() if not item["found"]]


def validate_required_assets() -> None:
    missing = missing_required_assets()
    if not missing:
        return
    lines = [f"{item['display_name']}: {item['expected_names']}" for item in missing]
    raise RuntimeError(
        "Required component images are missing.\n\n"
        f"Place these inside: {ASSETS_DIR}\n\n" + "\n".join(lines)
    )


def display_label(node) -> str:
    label = " ".join(str(getattr(node, "label", "") or "").split())
    return label or str(getattr(node, "id", "Component")).replace("_", " ").title()


def build_component_selection_df(selected_names: list[str] | None = None) -> pd.DataFrame:
    """Build the fixed component table used by the checkbox selector."""
    selected_set = set(selected_names or [])
    rows = []
    for index, item in enumerate(COMPONENT_CATALOG, start=1):
        rows.append(
            {
                "Select": item.name in selected_set,
                "#": index,
                "Component Type": item.group,
                "Component": item.name,
                "Code": item.code,
                "Details": item.connection_label,
            }
        )
    return pd.DataFrame(rows)


def asset_signature_for_hashing(root_dir: Path) -> str:
    """Return a stable signature that changes whenever component assets change.

    This fixes the old-image caching problem in component-selection mode: if the
    user replaces an image with a newer one but keeps the same component table
    selection, the generated output must still regenerate automatically.
    """
    if not root_dir.exists():
        return ""

    parts: list[str] = []
    for path in sorted(root_dir.rglob('*')):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            parts.append(f"{path.relative_to(root_dir)}:{digest}")
        except OSError:
            continue
    return '|'.join(parts)


def render_outputs(diagram) -> None:
    """Use the existing renderer for PNG, PPT and PDF in both input modes."""
    preview_png = create_preview_png(diagram=diagram, assets_dir=ASSETS_DIR)
    pptx_bytes = create_powerpoint(diagram=diagram, assets_dir=ASSETS_DIR)
    pdf_bytes = png_to_pdf(preview_png)

    st.session_state["diagram"] = diagram
    st.session_state["preview_png"] = preview_png
    st.session_state["pptx_bytes"] = pptx_bytes
    st.session_state["pdf_bytes"] = pdf_bytes


# =============================================================================
# GENERATION PIPELINES
# =============================================================================

def generate_professional_diagram(uploaded_bytes: bytes, orientation: str) -> None:
    """Existing sketch → AI topology → professional diagram workflow."""
    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    validate_required_assets()

    with st.status("Processing sketch and generating professional diagram...", expanded=True) as status:
        st.write("1/5  Loading hand-drawn image")
        original = resize_for_ai(rotate_image(load_image(uploaded_bytes), orientation))

        st.write("2/5  Enhancing handwriting and pipeline geometry with OpenCV")
        enhanced = enhance_sketch(original)

        client = get_gemini_client()

        st.write("3/5  Sketch Understanding Agent extracting components and exact connections")
        extracted = analyze_sketch(
            client=client,
            model=model,
            original_image=original,
            enhanced_image=enhanced,
        )

        st.write("4/5  Engineering Review Agent validating topology and layout")
        reviewed = review_diagram(client=client, model=model, diagram=extracted)

        st.write("5/5  Rendering premium PNG, editable PowerPoint and PDF")
        render_outputs(reviewed)
        status.update(label="Diagram created successfully", state="complete", expanded=False)


def generate_selected_components(selected_components: list[str]) -> None:
    """New selection → auto-layout → auto-connections → existing renderer workflow."""
    diagram = build_selected_component_diagram(selected_components)
    render_outputs(diagram)


# =============================================================================
# HEADER
# =============================================================================

st.markdown(
    """
<div class="premium-header">
  <div class="brand-wrap">
    <div class="brand-icon">💧</div>
    <div>
      <div class="brand-title">Agentic Sketch-to-PPT</div>
      <div class="brand-subtitle">Convert Your Sketch to Professional Diagrams & PowerPoint</div>
    </div>
  </div>
  <div class="steps">
    <div class="step"><div class="step-dot active">1</div><span>Upload & Select</span></div>
    <div class="step-arrow">→</div>
    <div class="step"><div class="step-dot">2</div><span>Process & Configure</span></div>
    <div class="step-arrow">→</div>
    <div class="step"><div class="step-dot">3</div><span>Generate & Download</span></div>
  </div>
</div>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# MAIN WORKSPACE
# =============================================================================

uploaded_file = None
orientation = "Auto / No rotation"

# Keep table selections stable across Streamlit reruns.
if "selected_components" not in st.session_state:
    st.session_state["selected_components"] = []

left_col, center_col, right_col = st.columns([1.05, 1.28, 0.78], gap="small")

with left_col:
    # -------------------------------------------------------------------------
    # 1. Upload Sketch - existing workflow remains available.
    # -------------------------------------------------------------------------
    st.markdown('<div class="panel-title">1. Upload Your Sketch</div>', unsafe_allow_html=True)
    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "Drag & drop your sketch here or click to browse",
            type=["png", "jpg", "jpeg", "webp"],
            help=(
                "Optional. Upload one hand-drawn engineering diagram. "
                "When one or more components are checked below, the selected-component "
                "diagram takes priority and only those checked components are rendered."
            ),
        )
        orientation = st.selectbox(
            "Image orientation",
            ["Auto / No rotation", "90° clockwise", "90° counter-clockwise", "180°"],
            index=0,
        )
        if uploaded_file is None:
            st.caption("Upload a sketch to use the existing AI extraction workflow.")
        else:
            st.success("Sketch uploaded. You may also select components from the table below.")

    # -------------------------------------------------------------------------
    # 2. Select Components - ALWAYS visible directly below Upload Sketch.
    # -------------------------------------------------------------------------
    st.markdown('<div class="panel-title">2. Select Components (Table)</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.caption(
            "Check only the components required in the final diagram. "
            "The generated diagram updates automatically whenever the selection changes."
        )

        # Seed values are recreated from the last accepted selection. The data_editor
        # widget keeps its own edit state through reruns using the stable key below.
        component_table = build_component_selection_df(
            st.session_state.get("selected_components", [])
        )

        edited_table = st.data_editor(
            component_table,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key="component_selection_editor",
            column_config={
                "Select": st.column_config.CheckboxColumn(
                    "Select",
                    help="Include this component in the generated diagram",
                    default=False,
                    width="small",
                ),
                "#": st.column_config.NumberColumn("#", width="small"),
                "Component Type": st.column_config.TextColumn(
                    "Component Type", width="medium"
                ),
                "Component": st.column_config.TextColumn(
                    "Component", width="large"
                ),
                "Code": st.column_config.TextColumn("Code", width="small"),
                "Details": st.column_config.TextColumn(
                    "Connection", width="medium"
                ),
            },
            disabled=["#", "Component Type", "Component", "Code", "Details"],
        )

        selected_components = edited_table.loc[
            edited_table["Select"].fillna(False), "Component"
        ].tolist()
        st.session_state["selected_components"] = selected_components

        if selected_components:
            st.success(
                f"{len(selected_components)} component(s) selected. "
                "Only these components will appear in the generated diagram."
            )
        else:
            st.info(
                "No components selected. Check one or more rows to generate a "
                "component-based diagram."
            )

    # Preserve the existing component-image status without competing with the
    # reference-style selection table. It stays available as a collapsed section.
    with st.expander("Component / Rendering Setup", expanded=False):
        asset_status = get_component_asset_status()
        for _node_type, item in asset_status.items():
            c1, c2 = st.columns([0.30, 0.70])
            with c1:
                if item["found"]:
                    st.image(str(item["path"]), use_container_width=True)
                else:
                    st.markdown("❌")
            with c2:
                st.markdown(f"**{item['display_name']}**")
                st.caption(
                    item["path"].name if item["found"] else item["expected_names"]
                )

        missing = missing_required_assets()
        if missing:
            st.warning(
                "Some real assets required by the original sketch workflow are missing. "
                "Component-table generation can still use the built-in professional cards."
            )
        else:
            st.success("Existing real component assets are configured.")


# =============================================================================
# INPUT PROCESSING / AUTOMATIC GENERATION
# =============================================================================

uploaded_bytes = uploaded_file.getvalue() if uploaded_file is not None else None
source_image = None
opencv_image = None
selected_components = st.session_state.get("selected_components", [])

# Selected components have priority because the requirement is that ONLY checked
# table rows are rendered when the user makes a table selection. If the table is
# empty, the original sketch-analysis workflow remains unchanged.
if selected_components:
    selection_signature = "|".join(selected_components)
    asset_signature = asset_signature_for_hashing(ASSETS_DIR)
    current_hash = hashlib.sha256(
        f"selection|{selection_signature}|assets|{asset_signature}".encode("utf-8")
    ).hexdigest()

    if st.session_state.get("processed_hash") != current_hash:
        try:
            with st.spinner(
                "Automatically arranging and connecting selected components..."
            ):
                generate_selected_components(selected_components)
            st.session_state["processed_hash"] = current_hash
        except Exception as exc:
            st.error("Automatic component diagram generation failed.")
            st.exception(exc)

elif uploaded_bytes is not None:
    source_image = rotate_image(load_image(uploaded_bytes), orientation)
    opencv_image = enhance_sketch(resize_for_ai(source_image))

    signature_parts = []
    for item in get_component_asset_status().values():
        path = item["path"]
        if path is not None:
            signature_parts.append(f"{path.resolve()}:{path.stat().st_mtime_ns}")

    current_hash = hashlib.sha256(
        b"sketch|"
        + uploaded_bytes
        + orientation.encode("utf-8")
        + "|".join(sorted(signature_parts)).encode("utf-8")
    ).hexdigest()

    if (
        st.session_state.get("processed_hash") != current_hash
        and not missing_required_assets()
    ):
        try:
            generate_professional_diagram(uploaded_bytes, orientation)
            st.session_state["processed_hash"] = current_hash
        except Exception as exc:
            st.error("Diagram generation failed.")
            st.exception(exc)

else:
    # Nothing is selected and no sketch exists, therefore an earlier output should
    # not remain visible as if it still represented the current input state.
    if st.session_state.get("diagram") is not None:
        reset_outputs()


# =============================================================================
# GENERATED DIAGRAM
# =============================================================================

with center_col:
    title = "3. Generated Diagram"
    if st.session_state.get("diagram") is not None:
        diagram = st.session_state["diagram"]
        visible_count = sum(
            1
            for node in diagram.nodes
            if getattr(node, "node_type", "") != "junction"
        )
        title = (
            f"3. Generated Diagram "
            f"({visible_count} components / {len(diagram.edges)} connections)"
        )

    st.markdown(f'<div class="panel-title">{title}</div>', unsafe_allow_html=True)

    with st.container(border=True):
        if st.session_state.get("preview_png") is not None:
            pill_col, _ = st.columns([0.45, 0.55])
            with pill_col:
                st.markdown(
                    '<span class="success-pill">✓ Diagram Created Successfully</span>',
                    unsafe_allow_html=True,
                )
            st.image(st.session_state["preview_png"], use_container_width=True)

        elif source_image is not None:
            tab1, tab2 = st.tabs(["Uploaded Sketch", "OpenCV Enhanced"])
            with tab1:
                st.image(source_image, use_container_width=True)
            with tab2:
                st.image(opencv_image, use_container_width=True)
            st.caption("The professional diagram will appear here after processing.")

        else:
            st.markdown(
                """
                <div style="min-height:640px;display:flex;align-items:center;
                            justify-content:center;text-align:center;color:#6d83a2;">
                    <div>
                        <div style="font-size:66px">⬆️</div>
                        <b>Upload a sketch or select components from the table.</b><br>
                        <span style="font-size:13px">
                            When components are checked, only those checked components
                            are automatically arranged, connected and rendered.
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# =============================================================================
# DETAILS / EXPORTS
# =============================================================================

with right_col:
    st.markdown('<div class="panel-title">4. Output / Component Details</div>', unsafe_allow_html=True)

    diagram = st.session_state.get("diagram")
    if diagram is None:
        with st.container(border=True):
            st.info("Component details and export options will appear here after generation.")
    else:
        for node in diagram.nodes:
            if getattr(node, "node_type", "") == "junction":
                continue
            with st.container(border=True):
                img_col, detail_col = st.columns([0.36, 0.64])
                with img_col:
                    asset = node_component_asset_path(ASSETS_DIR, node)
                    if asset is not None:
                        st.image(str(asset), use_container_width=True)
                    else:
                        code = next(
                            (
                                str(detail).split(":", 1)[1].strip()
                                for detail in getattr(node, "details", []) or []
                                if str(detail).lower().startswith("code:")
                            ),
                            getattr(node, "node_type", "COMP").upper(),
                        )
                        st.markdown(
                            f"<div style='height:72px;border:1px solid #bcd7f5;border-radius:10px;background:#eef7ff;display:flex;align-items:center;justify-content:center;color:#073c78;font-weight:800;font-size:18px'>{code}</div>",
                            unsafe_allow_html=True,
                        )
                with detail_col:
                    st.markdown(f"**{display_label(node)}**")
                    st.caption(f"Type: {getattr(node, 'node_type', 'other').title()}")
                    details = list(getattr(node, "details", []) or [])[:4]
                    for detail in details:
                        st.markdown(f"<span class='mini-note'>• {detail}</span>", unsafe_allow_html=True)
                    st.caption(f"Confidence: {safe_confidence(getattr(node, 'confidence', 0))}")

        with st.container(border=True):
            st.markdown("**Connection Summary**")
            rows = []
            nodes_by_id = {node.id: display_label(node) for node in diagram.nodes}
            for edge in diagram.edges:
                rows.append(
                    {
                        "From": nodes_by_id.get(edge.source, edge.source),
                        "To": nodes_by_id.get(edge.target, edge.target),
                        "Connection": edge.label or edge.pipe_size or "—",
                    }
                )
            if rows:
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                    height=min(330, 38 + 34 * max(1, len(rows))),
                )
            else:
                st.caption("No connections are required for a single selected component.")

        with st.container(border=True):
            st.markdown("**Export Options**")
            st.download_button(
                "⬇ Download Image (PNG)",
                st.session_state["preview_png"],
                "professional_site_diagram.png",
                "image/png",
                use_container_width=True,
            )
            st.download_button(
                "⬇ Download PPT (PowerPoint)",
                st.session_state["pptx_bytes"],
                "professional_site_diagram.pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                use_container_width=True,
            )
            st.download_button(
                "⬇ Download PDF",
                st.session_state["pdf_bytes"],
                "professional_site_diagram.pdf",
                "application/pdf",
                use_container_width=True,
            )


# =============================================================================
# EXISTING ENGINEERING DETAILS / DEBUG OUTPUT
# =============================================================================

if st.session_state.get("diagram") is not None:
    diagram = st.session_state["diagram"]
    with st.expander("AI interpretation details / engineering JSON"):
        component_rows = [
            {
                "Name": display_label(node),
                "Type": node.node_type,
                "Confidence": safe_confidence(getattr(node, "confidence", 0)),
                "Details": ", ".join(getattr(node, "details", []) or []),
            }
            for node in diagram.nodes
        ]
        st.markdown("#### Components")
        st.dataframe(pd.DataFrame(component_rows), use_container_width=True, hide_index=True)

        connection_rows = [
            {
                "From": edge.source,
                "To": edge.target,
                "Pipe Size": edge.pipe_size,
                "Label": edge.label,
                "Confidence": safe_confidence(getattr(edge, "confidence", 0)),
            }
            for edge in diagram.edges
        ]
        st.markdown("#### Connections")
        st.dataframe(pd.DataFrame(connection_rows), use_container_width=True, hide_index=True)

        if diagram.warnings:
            st.markdown("#### AI warnings")
            for warning in diagram.warnings:
                st.warning(warning)

        st.markdown("#### Engineering JSON")
        st.json(json.loads(diagram.model_dump_json()))

    if st.button("↻ Regenerate Diagram", use_container_width=True):
        st.session_state.pop("processed_hash", None)
        st.rerun()


st.markdown(
    """
<div class="footer-bar">
  <span><b>Agentic Sketch-to-PPT</b> &nbsp;|&nbsp; Smart • Accurate • Professional</span>
  <span>Better Diagrams. Smarter Presentations.</span>
</div>
    """,
    unsafe_allow_html=True,
)

        st.markdown("#### Engineering JSON")
        st.json(json.loads(diagram.model_dump_json()))

    if st.button("↻ Regenerate Diagram", use_container_width=True):
        st.session_state.pop("processed_hash", None)
        st.rerun()


st.markdown(
    """
<div class="footer-bar">
  <span><b>Agentic Sketch-to-PPT</b> &nbsp;|&nbsp; Smart • Accurate • Professional</span>
  <span>Better Diagrams. Smarter Presentations.</span>
</div>
    """,
    unsafe_allow_html=True,
)

