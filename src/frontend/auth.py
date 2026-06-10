import os
import streamlit as st
from ui import apply_theme, hero

_PALM_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="110" height="160" viewBox="0 0 110 160" fill="none">
  <!-- trunk -->
  <path d="M55 160 C52 138 48 112 53 82" stroke="#10b981" stroke-width="7"
        stroke-linecap="round" fill="none"/>
  <!-- fronds -->
  <path d="M53 82 C35 72 14 68  2 56" stroke="#10b981" stroke-width="3.5"
        stroke-linecap="round" fill="none"/>
  <path d="M53 82 C38 66 26 50 28 34" stroke="#2dd4bf" stroke-width="3.5"
        stroke-linecap="round" fill="none"/>
  <path d="M53 82 C50 62 50 42 53 22" stroke="#10b981" stroke-width="3.5"
        stroke-linecap="round" fill="none"/>
  <path d="M53 82 C68 66 80 50 78 34" stroke="#2dd4bf" stroke-width="3.5"
        stroke-linecap="round" fill="none"/>
  <path d="M53 82 C72 72 94 68 106 56" stroke="#10b981" stroke-width="3.5"
        stroke-linecap="round" fill="none"/>
  <!-- leaf tufts at frond tips -->
  <circle cx="2"   cy="52"  r="5" fill="#10b981" opacity="0.7"/>
  <circle cx="28"  cy="30"  r="5" fill="#2dd4bf" opacity="0.7"/>
  <circle cx="53"  cy="18"  r="5" fill="#10b981" opacity="0.7"/>
  <circle cx="78"  cy="30"  r="5" fill="#2dd4bf" opacity="0.7"/>
  <circle cx="106" cy="52"  r="5" fill="#10b981" opacity="0.7"/>
  <!-- coconuts -->
  <circle cx="50" cy="82" r="5" fill="#065f46" opacity="0.8"/>
  <circle cx="57" cy="86" r="4" fill="#065f46" opacity="0.8"/>
  <circle cx="44" cy="87" r="4" fill="#065f46" opacity="0.8"/>
</svg>
"""

_PALMS_CSS = (
    "<style>"
    ".refi-palm { position: fixed; pointer-events: none; z-index: 0; opacity: 0.28; }"
    ".refi-palm-bl { bottom: -8px; left: 16px; }"
    ".refi-palm-br { bottom: -8px; right: 16px; transform: scaleX(-1); }"
    ".refi-palm-tl { top: 56px; left: 30px; transform: scale(0.55) rotate(-12deg); opacity: 0.18; }"
    ".refi-palm-tr { top: 56px; right: 30px; transform: scale(0.55) scaleX(-1) rotate(-12deg); opacity: 0.18; }"
    "</style>"
    '<div class="refi-palm refi-palm-bl">' + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-br">' + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-tl">' + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-tr">' + _PALM_SVG + "</div>"
)


def require_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return

    apply_theme()
    st.markdown(_PALMS_CSS, unsafe_allow_html=True)

    hero(
        title_html="Welcome to Refi<span>AI</span>",
        subtitle="Please provide a valid password to continue.",
        badge="Secure access",
    )

    col, _ = st.columns([1, 1])
    with col:
        password = st.text_input("Password", type="password", placeholder="Enter password")
        login = st.button("Login  →", use_container_width=True)

    if login:
        app_password = os.getenv("APP_PASSWORD", "refinance")
        if password == app_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")

    st.stop()
