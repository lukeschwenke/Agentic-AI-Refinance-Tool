"""Shared UI theming for the RefiAI Streamlit app.

`apply_theme()` injects the dark-fintech / emerald look (fonts, gradients, glassy
cards, snappy buttons). `hero()` renders the branded landing header. Keep all
visual styling here so the 4 pages stay consistent.
"""
import streamlit as st

# Emerald / teal on deep navy — the RefiAI palette.
ACCENT = "#10b981"
ACCENT_2 = "#2dd4bf"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
  --refi-bg: #0a0f1a;
  --refi-surface: rgba(255,255,255,0.045);
  --refi-border: rgba(255,255,255,0.09);
  --refi-accent: #10b981;
  --refi-accent2: #2dd4bf;
  --refi-text: #e8eef6;
  --refi-muted: #93a2b8;
}

/* ---- Typography ---- */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
}
h1, h2, h3, h4 { letter-spacing: -0.025em !important; font-weight: 700 !important; }

/* ---- App background: deep navy with emerald aurora glows ---- */
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1200px 600px at 12% -8%, rgba(16,185,129,0.13), transparent 60%),
    radial-gradient(1000px 520px at 105% 4%, rgba(45,212,191,0.10), transparent 55%),
    var(--refi-bg);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; }

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
  background: rgba(9,13,22,0.92);
  border-right: 1px solid var(--refi-border);
  backdrop-filter: blur(14px);
}
[data-testid="stSidebarNav"] a {
  border-radius: 10px;
  transition: background .15s ease, color .15s ease;
}
[data-testid="stSidebarNav"] a:hover { background: rgba(16,185,129,0.10); }
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: rgba(16,185,129,0.14);
  color: #fff;
}

/* ---- Text inputs ---- */
[data-testid="stTextInput"] input {
  background: rgba(255,255,255,0.035) !important;
  border: 1px solid var(--refi-border) !important;
  border-radius: 12px !important;
  color: var(--refi-text) !important;
  padding: 0.72rem 0.95rem !important;
  transition: border-color .15s ease, box-shadow .15s ease;
}
[data-testid="stTextInput"] input:focus {
  border-color: var(--refi-accent) !important;
  box-shadow: 0 0 0 3px rgba(16,185,129,0.20) !important;
}
[data-testid="stTextInput"] label p { color: var(--refi-muted) !important; font-weight: 500; }

/* ---- Buttons: emerald gradient, snappy hover lift ---- */
.stButton > button {
  background: linear-gradient(135deg, #10b981, #2dd4bf) !important;
  color: #06121d !important;
  font-weight: 700 !important;
  border: 0 !important;
  border-radius: 12px !important;
  padding: 0.66rem 1.25rem !important;
  box-shadow: 0 8px 24px rgba(16,185,129,0.25);
  transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
}
.stButton > button:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 32px rgba(16,185,129,0.40);
  filter: brightness(1.06);
}
.stButton > button:active { transform: translateY(0); }

/* ---- Metric cards ---- */
[data-testid="stMetric"] {
  background: var(--refi-surface);
  border: 1px solid var(--refi-border);
  border-radius: 16px;
  padding: 1rem 1.1rem;
  backdrop-filter: blur(8px);
  transition: transform .15s ease, border-color .15s ease;
}
[data-testid="stMetric"]:hover { transform: translateY(-2px); border-color: rgba(16,185,129,0.45); }
[data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 800 !important; font-size: 1.7rem !important; }
[data-testid="stMetricLabel"] p { color: var(--refi-muted) !important; font-weight: 600 !important; }

/* ---- Bordered containers act as glass cards ---- */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--refi-surface);
  border: 1px solid var(--refi-border) !important;
  border-radius: 18px !important;
  backdrop-filter: blur(8px);
}

/* ---- Alerts ---- */
[data-testid="stAlert"] { border-radius: 14px; }

/* ---- Hero ---- */
.refi-hero { margin: 0.2rem 0 1.4rem 0; }
.refi-badge {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 0.8rem; font-weight: 600; color: var(--refi-accent2);
  background: rgba(16,185,129,0.10);
  border: 1px solid rgba(16,185,129,0.30);
  padding: 5px 12px; border-radius: 999px; margin-bottom: 16px;
}
.refi-badge .dot {
  width: 7px; height: 7px; border-radius: 50%; background: var(--refi-accent);
  box-shadow: 0 0 0 0 rgba(16,185,129,0.7); animation: refipulse 2s infinite;
}
@keyframes refipulse {
  0% { box-shadow: 0 0 0 0 rgba(16,185,129,0.6); }
  70% { box-shadow: 0 0 0 8px rgba(16,185,129,0); }
  100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
}
.refi-title {
  font-size: 3.4rem; font-weight: 900; line-height: 1.02; margin: 0 0 0.5rem 0;
  letter-spacing: -0.04em; color: #fff;
}
.refi-title span {
  background: linear-gradient(120deg, #10b981, #2dd4bf);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.refi-sub { color: var(--refi-muted); font-size: 1.08rem; line-height: 1.6; max-width: 640px; margin: 0; }
.refi-pills { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
.refi-pill {
  font-size: 0.82rem; font-weight: 600; color: var(--refi-text);
  background: rgba(255,255,255,0.04); border: 1px solid var(--refi-border);
  padding: 7px 13px; border-radius: 999px;
}

/* ---- Section label ---- */
.refi-eyebrow {
  text-transform: uppercase; letter-spacing: 0.14em; font-size: 0.72rem;
  font-weight: 700; color: var(--refi-accent2); margin-bottom: 2px;
}

/* ---- Recommendation card ---- */
.refi-reco {
  font-size: 1.06rem; line-height: 1.7; color: var(--refi-text);
}
</style>
"""


def apply_theme():
    """Inject the RefiAI dark-fintech theme. Call once at the top of every page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title_html: str, subtitle: str, pills: list[str] | None = None,
         badge: str | None = None):
    """Render the branded gradient hero header.

    `title_html` may contain a <span> to gradient-highlight part of the title.
    """
    pills = pills or []
    badge_html = (
        f'<div class="refi-badge"><span class="dot"></span>{badge}</div>' if badge else ""
    )
    pills_html = "".join(f'<span class="refi-pill">{p}</span>' for p in pills)
    st.markdown(
        f"""
        <div class="refi-hero">
          {badge_html}
          <h1 class="refi-title">{title_html}</h1>
          <p class="refi-sub">{subtitle}</p>
          <div class="refi-pills">{pills_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, subtitle: str | None = None):
    """Lighter header for the secondary pages — keeps them consistent with the hero."""
    sub = f'<p class="refi-sub" style="margin-top:8px;">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f"""
        <div class="refi-hero" style="margin-bottom:1.1rem;">
          <div class="refi-eyebrow">{eyebrow}</div>
          <h1 class="refi-title" style="font-size:2.4rem;margin-top:2px;">{title}</h1>
          {sub}
        </div>
        """,
        unsafe_allow_html=True,
    )


def fmt_pct(v) -> str:
    return f"{v:.3f}%" if isinstance(v, (int, float)) else "—"


def fmt_money(v) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "—"


def fmt_months(v) -> str:
    return f"{v:.1f}" if isinstance(v, (int, float)) else "—"
