import streamlit as st
from pathlib import Path
from ui import apply_theme, page_header

st.set_page_config(page_title="AWS Architecture", page_icon="🏡", layout="wide")
apply_theme()

page_header(
    "Infrastructure",
    "AWS Architecture",
    "How RefiAI is containerized, deployed, and runs in the cloud.",
)

FRONTEND_DIR = Path(__file__).resolve().parents[1]
IMG_PATH = FRONTEND_DIR / "images" / "arch_diagram_v3.png"

_, mid, _ = st.columns([1, 6, 1])
with mid:
    with st.container(border=True):
        st.image(str(IMG_PATH), width="stretch")
