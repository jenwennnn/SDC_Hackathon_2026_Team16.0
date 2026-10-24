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
TAGLINE = ("Your job is changing one task at a time. See which of your tasks AI may "
           "take over, which roles fit you next, and a free or low-cost plan to get there.")
CONTROL_NOTE = "Estimates to support your decision. You stay in control."

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
.stApp { background: #FFFFFF; }
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
.v-note { font-size: 13px; color: var(--v-ink); margin-top: 10px; font-weight: 500; }
@media (max-width: 760px) { .v-title { font-size: 40px; } .v-tagline { font-size: 16px; } }

/* ---------- cards (containers with a key starting with "card") ---------- */
[class*="st-key-card"] {
  background: #FFFFFF !important;
  border: 1px solid var(--v-border) !important;
  border-radius: var(--v-radius-lg) !important;
  box-shadow: var(--v-shadow);
  padding: 20px 22px !important;
}

/* ---------- buttons ---------- */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"] {
  border-radius: 6px !important;
  font-weight: 500;
  min-height: 40px;
  transition: background var(--v-t), border-color var(--v-t), color var(--v-t);
  box-shadow: none !important;
}
[data-testid="stBaseButton-primary"] {
  background: var(--v-ink) !important; border: 1px solid var(--v-ink) !important;
}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primary"] p { color: #FFFFFF !important; }
[data-testid="stBaseButton-primary"]:hover:not(:disabled) {
  background: #383838 !important; border-color: #383838 !important;
}
[data-testid="stBaseButton-secondary"] {
  background: #FFFFFF !important; border: 1px solid var(--v-border) !important;
}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondary"] p { color: var(--v-ink) !important; }
[data-testid="stBaseButton-secondary"]:hover:not(:disabled) {
  background: var(--v-hover) !important; border-color: var(--v-border-strong) !important;
}
[data-testid="stBaseButton-primary"]:disabled,
[data-testid="stBaseButton-secondary"]:disabled {
  background: var(--v-surface) !important; border-color: var(--v-border) !important;
}
[data-testid="stBaseButton-primary"]:disabled p,
[data-testid="stBaseButton-secondary"]:disabled p { color: #A1A1A1 !important; }
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

@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero():
    st.markdown(
        '<div class="v-hero">'
        f'<span class="v-kicker"><span class="dot"></span>{html.escape(KICKER)}</span>'
        f'<div class="v-title" role="heading" aria-level="1">{html.escape(TITLE)}</div>'
        f'<p class="v-tagline">{html.escape(TAGLINE)}</p>'
        f'<div class="v-note">{html.escape(CONTROL_NOTE)}</div>'
        '</div>',
        unsafe_allow_html=True)