"""Optional Streamlit example for uploading/replacing component artwork.

Copy only the small UI block you want into your existing settings area.
The diagram renderer itself does not depend on this example file.
"""

import streamlit as st

from src.component_image_paths import (
    COMPONENT_IMAGE_PATHS,
    component_upload_folder,
    save_uploaded_component_image,
    set_component_image_path,
)

st.caption(f"Component upload folder: {component_upload_folder()}")

component = st.selectbox("Component", list(COMPONENT_IMAGE_PATHS.keys()))
uploaded = st.file_uploader(
    "Upload component image",
    type=["png", "jpg", "jpeg", "webp", "bmp"],
)

if uploaded is not None and st.button("Use Uploaded Image"):
    saved_path = save_uploaded_component_image(component, uploaded)
    st.success(f"Saved: {saved_path}")

manual_path = st.text_input("Or enter an existing image file path")
if manual_path and st.button("Use Image Path"):
    saved_path = set_component_image_path(component, manual_path)
    st.success(f"Configured: {saved_path}")
