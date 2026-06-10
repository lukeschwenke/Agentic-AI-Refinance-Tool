import streamlit as st
from pathlib import Path
from ui import apply_theme, page_header
from auth import require_auth

st.set_page_config(page_title="Project Inspiration", page_icon="🏡", layout="wide")
require_auth()
apply_theme()

page_header(
    "The origin story",
    "Project Inspiration",
    "Why RefiAI exists — and how it keeps watching the market so you don't have to.",
)

FRONTEND_DIR = Path(__file__).resolve().parents[1]

col_text, col_image = st.columns([3, 2], gap="large", vertical_alignment="center")

with col_text:
    with st.container(border=True):
        st.markdown(
            """
            My wife and I went through the mortgage refinancing process in fall 2025 and it
            was very difficult to tell if it was actually an ideal time to refinance. Different
            lenders and people we talked to suggested various criteria to weigh whether
            refinancing was right for us. There was a big learning curve, but by the end I felt
            I had a good grasp on determining if refinancing was ideal — so I decided to
            integrate that logic into an agentic workflow that could be leveraged by myself and
            others in the future.
            """
        )

with col_image:
    st.image(str(FRONTEND_DIR / "images" / "inspiration_image.png"), width=300)

st.write("")
st.markdown('<div class="refi-eyebrow">Going further</div>', unsafe_allow_html=True)
st.markdown("#### Automating with daily emails")

with st.container(border=True):
    st.markdown(
        """
        To make future refinancing even easier, I built an AWS Lambda Python script with my
        personal mortgage details as environment variables, running daily at 11:00 AM via an
        AWS EventBridge schedule. An AWS SNS topic emails me the agentic summary with a clear
        answer on whether we should refinance. We no longer have to watch the markets closely —
        the 10-year Treasury yield or average interest rates. **The agents do the hard work.**
        """
    )

st.image(str(FRONTEND_DIR / "images" / "refi_daily_email.png"), width="stretch")
