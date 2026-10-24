"""
theme.py - the ShiftHappens look (Vercel-like: white, black, thin grey borders)

Base colours come from .streamlit/config.toml (light theme, Geist font).
This file adds the borders, buttons and cards on top.

    ink      #171717   text, primary buttons
    muted    #666666   secondary text
    border   #EAEAEA   1px borders everywhere
    surface  #FAFAFA   hover and quiet backgrounds
    blue     #0070F3   links, focus ring, notes
Colour is used only where it carries meaning (task baskets, rising/falling);
those colours live in signals_logic.py.

Cards: give a container a key that starts with "card", for example
    with st.container(border=True, key="card_tasks"):
Streamlit adds the class "st-key-card_tasks", and the CSS below styles it.

Used from app.py:
    inject_css()   once per run, before anything is drawn
    hero()         the title block at the top of every step
"""
import html

import streamlit as st

INK = "#171717"
MUTED = "#666666"
BORDER = "#EAEAEA"
SURFACE = "#FAFAFA"
BLUE = "#0070F3"

TITLE = "ShiftHappens"
KICKER = ("For office workers in admin, customer service, accounting support, "
          "data and content roles")
TAGLINE = "AI changes tasks, not whole jobs. Find your next move."

CSS = """
<style>
:root {
  --v-ink: #171717;
  --v-muted: #666666;
  --v-border: #EAEAEA;
  --v-border-strong: #D4D4D4;
  --v-surface: #FAFAFA;
  --v-hover: #F2F2F2;
  --v-blue: #0070F3;
  --v-radius: 8px;
  --v-radius-lg: 12px;
  --v-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  --v-t: 150ms;
}

/* ---------- page and type ---------- */
/* faint colour wash behind the page, so the glass buttons have something to blur */
.stApp {
  background:
    radial-gradient(900px 520px at 8% -8%, rgba(0, 112, 243, 0.09), transparent 62%),
    radial-gradient(800px 480px at 100% 4%, rgba(245, 166, 35, 0.09), transparent 60%),
    radial-gradient(700px 500px at 50% 110%, rgba(57, 142, 74, 0.06), transparent 60%),
    #FFFFFF;
  background-attachment: fixed;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stProgressBarTrack"] { background: #EAEAEA !important; }
[data-testid="stProgressBarTrack"] > div { background: var(--v-ink) !important; }
.block-container { padding-top: 2rem; max-width: 1200px; }
h1, h2, h3, h4 { letter-spacing: -0.03em; font-weight: 600 !important; color: var(--v-ink); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
  color: var(--v-muted) !important;
}
a, a:visited { color: var(--v-blue) !important; text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border-color: var(--v-border) !important; }
[data-testid="stCheckbox"] label p, [data-testid="stCheckbox"] label div {
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
}

/* ---------- hero ---------- */
.v-hero { padding: 8px 0 28px 0; margin-bottom: 20px; border-bottom: 1px solid var(--v-border); }
.v-kicker {
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid var(--v-border); border-radius: 999px; padding: 4px 12px;
  font-size: 13px; color: var(--v-muted); background: #FFFFFF;
}
.v-kicker .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--v-blue); }
.v-title { font-size: 56px; line-height: 1.05; font-weight: 700; letter-spacing: -0.05em;
           color: var(--v-ink); margin: 16px 0 12px 0; }
.v-tagline { font-size: 18px; line-height: 1.55; color: var(--v-muted); margin: 0; max-width: 760px; }
@media (max-width: 760px) { .v-title { font-size: 40px; } .v-tagline { font-size: 16px; } }

/* ---------- cards: frosted glass, cursor light and border glow (see fx.py) ---------- */
[class*="st-key-card"] {
  position: relative; isolation: isolate;
  background: rgba(255, 255, 255, 0.62) !important;
  -webkit-backdrop-filter: blur(18px) saturate(160%); backdrop-filter: blur(18px) saturate(160%);
  border: 1px solid rgba(0, 0, 0, 0.07) !important;
  border-radius: var(--v-radius-lg) !important;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 10px 30px rgba(0, 0, 0, 0.04),
              inset 0 1px 0 rgba(255, 255, 255, 0.85);
  padding: 20px 22px !important;
  transition: transform 500ms cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 300ms;
  will-change: transform;
}
[class*="st-key-card"].sh-lit {
  transition: transform 90ms linear, box-shadow 300ms;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04), 0 18px 44px rgba(0, 0, 0, 0.08),
              inset 0 1px 0 rgba(255, 255, 255, 0.9);
}
[class*="st-key-card"]::before {
  content: ""; position: absolute; inset: 0; border-radius: inherit; z-index: -1;
  pointer-events: none; opacity: 0; transition: opacity 300ms;
  background: radial-gradient(420px circle at var(--mx, 50%) var(--my, 50%),
              rgba(0, 112, 243, 0.08), rgba(255, 255, 255, 0) 62%);
}
[class*="st-key-card"]::after {
  content: ""; position: absolute; inset: -1px; border-radius: inherit; padding: 1px;
  pointer-events: none; opacity: 0; transition: opacity 300ms;
  background: radial-gradient(240px circle at var(--mx, 50%) var(--my, 50%),
              rgba(0, 112, 243, 0.55), rgba(0, 112, 243, 0) 70%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
}
[class*="st-key-card"].sh-lit::before, [class*="st-key-card"].sh-lit::after { opacity: 1; }

/* ---------- rolling numbers (see fx.roll) ---------- */
@property --sh-n { syntax: "<integer>"; inherits: false; initial-value: 0; }
.v-roll { counter-reset: shn var(--sh-n); display: inline-block; font-variant-numeric: tabular-nums; }
.v-roll::after { content: counter(shn); }
.v-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.st-key-fxbridge { position: absolute !important; width: 0; height: 0; overflow: hidden; }

/* ---------- buttons: liquid glass ---------- */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {
  border-radius: 999px !important;
  font-weight: 500;
  min-height: 40px;
  -webkit-backdrop-filter: blur(14px) saturate(180%);
  backdrop-filter: blur(14px) saturate(180%);
  transition: background var(--v-t), box-shadow var(--v-t), transform var(--v-t);
}
[data-testid="stBaseButton-secondary"] {
  background: rgba(255, 255, 255, 0.55) !important;
  border: 1px solid rgba(0, 0, 0, 0.08) !important;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06),
              inset 0 1px 0 rgba(255, 255, 255, 0.9),
              inset 0 -1px 0 rgba(0, 0, 0, 0.03) !important;
}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondary"] p { color: var(--v-ink) !important; }
[data-testid="stBaseButton-secondary"]:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.8) !important;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.09), inset 0 1px 0 rgba(255, 255, 255, 1) !important;
}
[data-testid="stBaseButton-primary"] {
  background: rgba(23, 23, 23, 0.86) !important;
  border: 1px solid rgba(255, 255, 255, 0.18) !important;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18),
              inset 0 1px 0 rgba(255, 255, 255, 0.22) !important;
}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primary"] p { color: #FFFFFF !important; }
[data-testid="stBaseButton-primary"]:hover:not(:disabled) { background: rgba(23, 23, 23, 0.95) !important; }
[data-testid="stBaseButton-primary"]:active:not(:disabled),
[data-testid="stBaseButton-secondary"]:active:not(:disabled) { transform: scale(0.98); }
[data-testid="stBaseButton-primary"]:disabled,
[data-testid="stBaseButton-secondary"]:disabled {
  background: rgba(250, 250, 250, 0.5) !important; border-color: rgba(0, 0, 0, 0.06) !important;
  box-shadow: none !important;
}
[data-testid="stBaseButton-primary"]:disabled p,
[data-testid="stBaseButton-secondary"]:disabled p { color: #A1A1A1 !important; }

/* ---------- step bar: a glass capsule slides under the current step ---------- */
.st-key-navtrack {
  position: relative;
  background: rgba(0, 0, 0, 0.045);
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 999px;
  padding: 4px !important;
  gap: 0 !important;
}
.st-key-navtrack::before {
  content: ""; position: absolute; top: 4px; bottom: 4px; z-index: 0;
  left: calc(4px + (100% - 8px) * var(--nav-i) / var(--nav-n));
  right: calc(4px + (100% - 8px) * (var(--nav-n) - 1 - var(--nav-i)) / var(--nav-n));
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.62);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  backdrop-filter: blur(16px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.10),
              inset 0 1px 1px rgba(255, 255, 255, 1),
              inset 0 -1px 1px rgba(0, 0, 0, 0.04);
  /* the leading edge moves first and the trailing edge follows, so the capsule
     stretches in the direction of travel; the overshoot curve gives the bounce */
  transition:
    left var(--nav-left-dur) cubic-bezier(0.34, 1.56, 0.64, 1) var(--nav-left-delay),
    right var(--nav-right-dur) cubic-bezier(0.34, 1.56, 0.64, 1) var(--nav-right-delay);
}
.st-key-navtrack [data-testid="stHorizontalBlock"] { gap: 0 !important; }
.st-key-navtrack [data-testid="stBaseButton-primary"],
.st-key-navtrack [data-testid="stBaseButton-secondary"] {
  position: relative; z-index: 1;
  background: transparent !important; border: none !important; box-shadow: none !important;
  -webkit-backdrop-filter: none; backdrop-filter: none;
}
.st-key-navtrack [data-testid="stBaseButton-primary"],
.st-key-navtrack [data-testid="stBaseButton-primary"] p { color: var(--v-ink) !important; font-weight: 600; }
.st-key-navtrack [data-testid="stBaseButton-secondary"] p { color: var(--v-muted) !important; }
.st-key-navtrack [data-testid="stBaseButton-secondary"]:hover:not(:disabled) p { color: var(--v-ink) !important; }
.st-key-navtrack [data-testid="stBaseButton-secondary"]:disabled p { color: #B5B5B5 !important; }
.st-key-navtrack [data-testid="stBaseButton-primary"]:active,
.st-key-navtrack [data-testid="stBaseButton-secondary"]:active { transform: none; }

/* role names in the ranking are text links */
[data-testid="stBaseButton-tertiary"], [data-testid="stBaseButton-tertiary"] p {
  color: var(--v-ink) !important; font-weight: 500; text-align: left;
}
[data-testid="stBaseButton-tertiary"]:hover p { color: var(--v-blue) !important; text-decoration: underline; }
[class*="st-key-rolerow"] { border-bottom: 1px solid var(--v-border); padding: 2px 0; }
button:focus-visible, summary:focus-visible, [role="radio"]:focus-visible,
input:focus-visible, textarea:focus-visible {
  outline: 2px solid var(--v-blue) !important; outline-offset: 2px;
}

/* ---------- inputs ---------- */
[data-baseweb="select"] > div, [data-baseweb="textarea"], [data-baseweb="input"] {
  background: #FFFFFF !important; border-radius: 6px !important;
}
[data-testid="stFileUploaderDropzone"] {
  background: var(--v-surface) !important; border: 1px dashed var(--v-border-strong) !important;
  border-radius: var(--v-radius) !important;
}

/* ---------- notes (st.info and friends) ---------- */
[data-testid="stAlertContainer"] {
  border-radius: var(--v-radius) !important; border: 1px solid var(--v-border) !important;
  background: #FFFFFF !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
  background: #F0F7FF !important; border-color: #C2DCFF !important;
}
[data-testid="stAlertContentInfo"], [data-testid="stAlertContentInfo"] p {
  color: #0058C2 !important; font-weight: 500;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
  background: #FFF8EB !important; border-color: #FFE0A8 !important;
}
[data-testid="stAlertContentWarning"], [data-testid="stAlertContentWarning"] p { color: #8A5300 !important; }
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
  background: #FFF0F0 !important; border-color: #FFC9C9 !important;
}
[data-testid="stAlertContentError"], [data-testid="stAlertContentError"] p { color: #B4232A !important; }

/* ---------- disclosures ---------- */
[data-testid="stExpander"] details {
  background: #FFFFFF; border: 1px solid var(--v-border) !important;
  border-radius: var(--v-radius) !important; box-shadow: none;
}
[data-testid="stExpander"] summary:hover { background: var(--v-surface); }

/* ---------- numbers and tables ---------- */
[data-testid="stMetric"] {
  background: #FFFFFF; border: 1px solid var(--v-border);
  border-radius: var(--v-radius); padding: 12px 16px;
}
[data-testid="stMetricValue"] { letter-spacing: -0.03em; font-weight: 600; }
[data-testid="stDataFrame"] { border-radius: var(--v-radius); overflow: hidden; }
[role="dialog"] { border-radius: var(--v-radius-lg) !important; }

/* ---------- step 3 pieces ---------- */
.v-stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 14px 0; }
.v-stat {
  flex: 1 1 140px; border: 1px solid var(--v-border); border-radius: var(--v-radius);
  padding: 12px 14px; background: #FFFFFF;
}
.v-stat .n { font-size: 28px; font-weight: 600; letter-spacing: -0.03em; line-height: 1.1; }
.v-stat .t { font-size: 13px; color: var(--v-muted); display: flex; align-items: center; gap: 6px; }
.v-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex: 0 0 8px; }
.v-badge {
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid var(--v-border); border-radius: 999px; padding: 4px 12px;
  font-weight: 500; font-size: 14px; background: #FFFFFF;
}
.v-card {
  border: 1px solid var(--v-border); border-radius: var(--v-radius); margin: 8px 0;
  padding: 10px 12px; background: #FFFFFF; transition: border-color var(--v-t);
}
.v-card:hover { border-color: var(--v-border-strong); }
.v-card summary { cursor: pointer; list-style: none; display: flex; gap: 10px; align-items: flex-start; }
.v-card summary::-webkit-details-marker { display: none; }
.v-num {
  flex: 0 0 24px; height: 24px; border-radius: 50%; text-align: center;
  font-size: 12px; font-weight: 600; line-height: 24px;
}
.v-card .lbl { font-size: 15px; line-height: 1.4; color: var(--v-ink); }
.v-card .sub { font-size: 13px; color: var(--v-muted); margin-top: 2px; }
.v-card .more { font-size: 13px; color: var(--v-blue); margin-top: 2px; }
.v-card[open] .more { display: none; }
.v-detail { font-size: 14px; line-height: 1.6; margin-top: 10px; color: var(--v-ink);
            border-top: 1px solid var(--v-border); padding-top: 8px; }
.v-compass svg { width: 100%; max-width: 380px; height: auto; display: block; margin: 0 auto; }

.v-course {
  display: flex; gap: 14px; align-items: flex-start;
  border: 1px solid var(--v-border); border-radius: var(--v-radius);
  padding: 12px 14px; margin: 8px 0; background: #FFFFFF;
}
.v-step {
  flex: 0 0 26px; height: 26px; border-radius: 50%; background: var(--v-ink); color: #FFFFFF;
  text-align: center; line-height: 26px; font-size: 13px; font-weight: 600;
}
.v-course-title { font-size: 15px; font-weight: 600; }
.v-course-title a { color: var(--v-ink) !important; }
.v-course-title a:hover { color: var(--v-blue) !important; }
.v-course-meta { font-size: 13px; color: var(--v-muted); margin-top: 2px; }
.v-course-teaches { font-size: 13px; margin-top: 4px; }

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
  .st-key-navtrack::before { transition: none !important; }
}
</style>
"""


def nav_capsule_style(index, count, direction):
    """Position of the step-bar capsule. direction > 0 = moving right, < 0 = left.
    The edge in front moves fast, the edge behind follows a little later."""
    lead = "380ms", "0ms"
    trail = "520ms", "70ms"
    if direction > 0:
        right, left = lead, trail
    elif direction < 0:
        left, right = lead, trail
    else:
        left = right = lead
    st.markdown(
        "<style>.st-key-navtrack {"
        f"--nav-i: {int(index)}; --nav-n: {int(count)};"
        f"--nav-left-dur: {left[0]}; --nav-left-delay: {left[1]};"
        f"--nav-right-dur: {right[0]}; --nav-right-delay: {right[1]};"
        "}</style>",
        unsafe_allow_html=True)


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero():
    st.markdown(
        '<div class="v-hero">'
        f'<span class="v-kicker"><span class="dot"></span>{html.escape(KICKER)}</span>'
        f'<div class="v-title" role="heading" aria-level="1">{html.escape(TITLE)}</div>'
        f'<p class="v-tagline">{html.escape(TAGLINE)}</p>'
        '</div>',
        unsafe_allow_html=True)