"""Shared UI theming for the RefiAI Streamlit app.

`apply_theme()` injects the dark-fintech / emerald look (fonts, gradients, glassy
cards, snappy buttons). `hero()` renders the branded landing header. Keep all
visual styling here so the 4 pages stay consistent.
"""
import streamlit as st

# Emerald / teal on deep navy — the RefiAI palette.
ACCENT = "#10b981"
ACCENT_2 = "#2dd4bf"

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

# Subtle fixed-position palms scattered around the viewport edges; they sit
# behind the content (z-index 0, pointer-events none) on every page.
_PALMS_HTML = (
    "<style>"
    ".refi-palm { position: fixed; pointer-events: none; z-index: 0; opacity: 0.28; }"
    ".refi-palm-bl  { bottom: -8px;  left: 16px;  }"
    ".refi-palm-br  { bottom: -8px;  right: 16px; transform: scaleX(-1); }"
    ".refi-palm-bl2 { bottom: -8px;  left: 140px; transform: scale(0.75) rotate(8deg); opacity: 0.20; }"
    ".refi-palm-br2 { bottom: -8px;  right: 140px; transform: scale(0.75) scaleX(-1) rotate(8deg); opacity: 0.20; }"
    ".refi-palm-ml  { top: 45%;  left: 10px;  transform: scale(0.65) rotate(-6deg);  opacity: 0.16; }"
    ".refi-palm-mr  { top: 45%;  right: 10px; transform: scale(0.65) scaleX(-1) rotate(-6deg); opacity: 0.16; }"
    ".refi-palm-tl  { top: 56px; left: 30px;  transform: scale(0.50) rotate(-14deg); opacity: 0.14; }"
    ".refi-palm-tr  { top: 56px; right: 30px; transform: scale(0.50) scaleX(-1) rotate(-14deg); opacity: 0.14; }"
    ".refi-palm-tl2 { top: 80px; left: 160px; transform: scale(0.35) rotate(10deg);  opacity: 0.10; }"
    ".refi-palm-tr2 { top: 80px; right: 160px; transform: scale(0.35) scaleX(-1) rotate(10deg); opacity: 0.10; }"
    "</style>"
    '<div class="refi-palm refi-palm-bl">'   + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-br">'   + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-bl2">'  + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-br2">'  + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-ml">'   + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-mr">'   + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-tl">'   + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-tr">'   + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-tl2">'  + _PALM_SVG + "</div>"
    '<div class="refi-palm refi-palm-tr2">'  + _PALM_SVG + "</div>"
)

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
[data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
  color: var(--refi-text);
}
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
/* Explicit high-contrast nav link colour so it stays legible even if the dark
   theme config never loads (e.g. browser falls back to a light base). */
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] a span {
  border-radius: 10px;
  color: #cdd9ea !important;
  transition: background .15s ease, color .15s ease;
}
[data-testid="stSidebarNav"] a:hover,
[data-testid="stSidebarNav"] a:hover span { background: rgba(16,185,129,0.10); color: #ffffff !important; }
[data-testid="stSidebarNav"] a[aria-current="page"],
[data-testid="stSidebarNav"] a[aria-current="page"] span {
  background: rgba(16,185,129,0.14);
  color: #ffffff !important;
}

/* ---- Text inputs ----
   Solid dark fill (not translucent white) with an explicit light text-fill, so
   typed text stays readable even if the dark theme config is missing and the
   browser falls back to a light base. The autofill rules stop the browser from
   repainting the field white-on-white. */
[data-testid="stTextInput"] input {
  background: #101725 !important;
  border: 1px solid var(--refi-border) !important;
  border-radius: 12px !important;
  color: var(--refi-text) !important;
  -webkit-text-fill-color: var(--refi-text) !important;
  caret-color: var(--refi-accent) !important;
  padding: 0.72rem 0.95rem !important;
  transition: border-color .15s ease, box-shadow .15s ease;
}
[data-testid="stTextInput"] input:focus {
  border-color: var(--refi-accent) !important;
  box-shadow: 0 0 0 3px rgba(16,185,129,0.20) !important;
}
[data-testid="stTextInput"] input::placeholder { color: var(--refi-muted) !important; opacity: 1; }
[data-testid="stTextInput"] input:-webkit-autofill,
[data-testid="stTextInput"] input:-webkit-autofill:hover,
[data-testid="stTextInput"] input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--refi-text) !important;
  -webkit-box-shadow: 0 0 0 1000px #101725 inset !important;
  caret-color: var(--refi-accent) !important;
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

/* ---- Footer: legal / disclaimers ---- */
.refi-footer {
  margin-top: 3.5rem; padding-top: 1.2rem;
  border-top: 1px solid var(--refi-border);
  font-size: 0.72rem; line-height: 1.6; color: var(--refi-muted);
  opacity: 0.85;
}
.refi-footer strong { color: var(--refi-text); font-weight: 600; }
</style>
"""


def apply_theme():
    """Inject the RefiAI dark-fintech theme. Call once at the top of every page."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(_PALMS_HTML, unsafe_allow_html=True)


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


def footer():
    """Small legal footer — call at the bottom of every page."""
    st.markdown(
        """
        <div class="refi-footer">
          <strong>Disclaimer:</strong> RefiAI is a personal demo project for educational purposes.
          It does not provide financial, legal, or tax advice, and nothing on this site is a loan
          offer, quote, or commitment to lend. Rates and calculations may be inaccurate or delayed —
          consult a licensed professional before making financial decisions.<br>
          <strong>Privacy:</strong> Mortgage inputs you submit and your IP address are logged to
          operate and rate-limit this demo. No data is sold or shared with third parties.<br>
          <strong>Terms:</strong> Provided "as is" without warranty of any kind; use at your own
          risk. Daily usage limits apply. &copy; 2026 Luke Schwenke.
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
