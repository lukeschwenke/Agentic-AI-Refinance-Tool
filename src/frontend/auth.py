import os
import streamlit as st
from ui import apply_theme, hero


def require_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return

    apply_theme()

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
