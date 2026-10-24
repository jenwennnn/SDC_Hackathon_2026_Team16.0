"""
app.py - ShiftHappens

A guided journey in five steps:
  1. Your background   - CV, role template, or a saved profile file
  2. Review            - confirm tasks and skills (human in the loop)
  3. Your day          - how AI may affect your daily tasks (trend signals)
  4. Your roles        - future roles that fit, pick a target role
  5. Your plan         - learning plan for the target role, SDG links, save profile
The step bar at the top is clickable, so users can jump back to any step they
have already reached. ONE set of data controls (AI progress scenario and trend
data batch, steps 3 to 5) is shared by all steps, so changing the batch changes
the day view, the role ranking and the plan together.

Data contract: final_profile keeps skills[].esco_id untouched for the matcher.
Nothing personal is stored on a server. Users keep their own profile file
(download under My profile, upload on the start screen to come back).
"""
import html
import json
import os
import re
from datetime import datetime, timezone
from io import StringIO

import docx
import pandas as pd
import PyPDF2
import streamlit as st
from dotenv import load_dotenv
from thefuzz import process

import results_page as rp
import signals_logic as sl
import trend_bridge as tb
import signals_views as sv
import fx
import intro
import theme

# ---------- Config (secrets come from environment variables, never from code) ----------
load_dotenv()
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
has_api_key = bool(LLM_API_KEY)
if has_api_key:
    import google.generativeai as genai
    genai.configure(api_key=LLM_API_KEY)

st.set_page_config(page_title="ShiftHappens", layout="wide")
theme.inject_css()

STEPS = ["Your background", "Review", "Your day", "Your roles", "Your plan"]
STEP_INTRO = {
    3: "Which of your daily tasks AI may take over, which it will assist with, and which stay yours.",
    4: "Future roles that fit your skills. Pick one as your target.",
    5: "Free and low-cost courses that close the gaps for your target role.",
}
SEED_FILE = "data/esco_skills_seed_v2.json"
TEMPLATE_FILE = "data/occupation_templates.json"
DEFAULT_GOALS = {"mode": "undecided", "interests": [], "sdg_importance": 0.3}
DEFAULT_CONSTRAINTS = {"hours_per_week": 5, "budget": "free", "timeline_months": 6, "language": "en"}


# ---------- Data ----------
@st.cache_data
def load_data():
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        esco_data = json.load(f)["skills"]
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        templates = json.load(f)["templates"]
    return esco_data, templates


try:
    esco_skills, occupation_templates = load_data()
    esco_skill_names = {s["name"]: s["esco_id"] for s in esco_skills}
except FileNotFoundError:
    st.error(f"Missing data files. Make sure {SEED_FILE} and {TEMPLATE_FILE} exist.")
    st.stop()


# ---------- Utilities ----------
def clean_label(text):
    """Display fix: remove citation markers and the UNSOURCED tag left in template task labels."""
    text = re.sub(r"\[cite:[^\]]*\]", "", text)
    text = text.replace("[UNSOURCED]", "")
    return text.strip()


PHONE_PATTERNS = [
    # Malaysian style numbers with spaces or dashes: +60 12-345 6789, 012-345 6789, 03-1234 5678
    r"(?<!\d)(?:\+?60[\s-]?|0)\d{1,2}[\s-]?\d{3,4}[\s-]?\d{4}(?!\d)",
    # any other run of 10 to 12 digits
    r"\+?\d{10,12}",
]


def strip_pii(text):
    """Remove emails, phone numbers and Malaysian IC numbers before text goes to the LLM."""
    text = re.sub(r"\S+@\S+", "[EMAIL REMOVED]", text)
    text = re.sub(r"\d{6}-\d{2}-\d{4}", "[IC REMOVED]", text)
    for pattern in PHONE_PATTERNS:
        text = re.sub(pattern, "[PHONE REMOVED]", text)
    return text


# ---------- Task categories (deterministic keyword rules, the user can change them) ----------
# Checked in this order; the first rule that matches wins.
TASK_TYPE_RULES = [
    ("relationship_building", ["relationship", "rapport", "trust", "vendor", "supplier",
                               "stakeholder", "negotiat", "mentor", "mediat",
                               "community", "communities"]),
    ("decision_judgement", ["decide", "decision", "judg", "prioriti", "approve", "compliance",
                            "complies", "comply", "deficienc", "discrepanc", "root issue",
                            "identify", "strateg", "save costs"]),
    ("calculation_reconciliation", ["reconcil", "verify", "verif", "accuracy", "audit",
                                    "calculat", "billing", "charges", "payroll calculation",
                                    "balance", "inventory", "supplies", "figures", "bank statement",
                                    "cross-check"]),
    ("data_analysis", ["analys", "analyz", "analytics", "dashboard", "insight", "statistic",
                       "forecast", "budgeting", "metrics"]),
    ("reporting_writing", ["report", "summar", "minutes", "assemble financial",
                           "presentation"]),
    ("content_creation", ["content", "social media", "post ", "posts", "campaign",
                          "copywrit", "design", "newsletter"]),
    ("physical_or_manual", [" mail ", "package", "parcel", "print", "photocop",
                            "stock"]),
    ("data_entry", ["enter ", "enters ", "entry", "entries", "input", "key in", "keying",
                    "typing", "record ", "records", "update ", "ledger", "transactions"]),
    ("scheduling_coordination", ["schedul", "calendar", "appointment", "diary", "diaries",
                                 "meeting", "travel", "coordinat", "organise daily",
                                 "workflow", "booking"]),
    ("document_processing", ["document", "file", "filing", "sort", "scan", "archive",
                             "paperwork", "retrieve", "compile", "time sheet", "timesheet",
                             "payroll", "pay checks", "invoice", "forms"]),
    ("customer_communication", ["customer", "client", "caller", "call", "inquir", "enquir",
                                "visitor", "telephone", "phone", "complain", "provide information"]),
    ("internal_communication", ["email", "memo", "internal", "colleague", "team", "management",
                                "manager", "pitch"]),
]


def guess_task_type(label):
    text = " " + str(label).lower() + " "
    for task_type, keywords in TASK_TYPE_RULES:
        if any(k in text for k in keywords):
            return task_type
    return None


def task_type_label(task_type):
    return sv.TASK_TYPE_NAMES.get(task_type, "No category")


def extract_text(file):
    if file.name.endswith(".pdf"):
        reader = PyPDF2.PdfReader(file)
        return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
    elif file.name.endswith(".docx"):
        document = docx.Document(file)
        return " ".join([para.text for para in document.paragraphs])
    return StringIO(file.getvalue().decode("utf-8")).read()


def match_esco_skill(skill_name):
    """Fuzzy match a skill name against the local ESCO seed."""
    best_match, score = process.extractOne(skill_name, list(esco_skill_names.keys()))
    if score >= 80:
        return esco_skill_names[best_match], True, best_match
    return None, False, skill_name


def clamp_level(value, default=3):
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return default


def extract_skills_llm(text, retries=1):
    if not has_api_key:
        st.session_state["last_error"] = "LLM_API_KEY not found. Check the location and variable name of your .env file."
        return None

    model = genai.GenerativeModel(LLM_MODEL)
    prompt = f"""
    Extract professional skills from the following CV text.
    Return ONLY a valid JSON object matching this schema perfectly:
    {{
      "skills": [
        {{"name": "Skill Name", "level": 3, "evidence": "Snippet from CV", "confidence": "high"}}
      ],
      "current_role": {{"title": "Latest Job Title", "industry": "Industry guess", "years_experience": "3-5", "tasks": ["Task 1"]}}
    }}
    Level is 1 (Beginner) to 5 (Expert). Confidence is "low", "medium", or "high".
    List the daily tasks of the latest job as short phrases that start with a verb.
    DO NOT include ESCO mapping or PII.
    CV Text: {text}
    """
    for attempt in range(retries + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text)
            role = data.get("current_role") or {}
            tasks = [str(t).strip() for t in role.get("tasks", []) if str(t).strip()]
            role["tasks"] = tasks
            role["task_type_map"] = {t: guess_task_type(t) for t in tasks}
            data["current_role"] = role
            data.setdefault("skills", [])
            for skill in data.get("skills", []):
                esco_id, mapped, matched_name = match_esco_skill(skill["name"])
                skill["esco_id"] = esco_id
                skill["mapped"] = mapped
                skill["name"] = matched_name if mapped else skill["name"]
                skill["level"] = clamp_level(skill.get("level"))
                skill["user_confirmed"] = False
            return data
        except Exception as e:
            st.session_state["last_error"] = f"{type(e).__name__}: {e}"
            if attempt == retries:
                return None


# ---------- Saved profile files ----------
def profile_from_upload(file):
    """Read a profile file saved earlier. Keeps only known fields. Returns (profile, error)."""
    try:
        data = json.loads(file.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "This file is not a valid ShiftHappens profile (JSON could not be read)."
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        return None, "This file is not a valid ShiftHappens profile (no skills list)."
    skills = []
    for s in data["skills"]:
        if isinstance(s, dict) and s.get("name"):
            skills.append({
                "name": str(s["name"]),
                "esco_id": s.get("esco_id"),
                "mapped": bool(s.get("esco_id")),
                "level": clamp_level(s.get("level")),
                "evidence": str(s.get("evidence", "")),
                "confidence": str(s.get("confidence", "")),
                "user_confirmed": True,
            })
    if not skills:
        return None, "The profile file has no skills."
    role = data.get("current_role") or {}
    details = [d for d in role.get("task_details", []) if isinstance(d, dict) and d.get("label")]
    tasks = [str(t) for t in role.get("tasks", [])] or [d["label"] for d in details]
    profile = {
        "source": data.get("source", "saved_profile"),
        "skills": skills,
        "current_role": {
            "title": str(role.get("title", "")),
            "industry": str(role.get("industry", "")),
            "years_experience": str(role.get("years_experience", "")),
            "tasks": tasks,
            "task_details": [{"label": d["label"], "task_type": d.get("task_type")} for d in details],
        },
        "goals": {**DEFAULT_GOALS, **(data.get("goals") or {})},
        "constraints": {**DEFAULT_CONSTRAINTS, **(data.get("constraints") or {})},
        "risk_preference": data.get("risk_preference", "stable"),
        "scenario_focus": data.get("scenario_focus", "both"),
        "meta": data.get("meta") or {"created_at": datetime.now(timezone.utc).isoformat()},
    }
    if profile["constraints"].get("budget") not in rp.BUDGETS:
        profile["constraints"]["budget"] = "free"
    if profile["constraints"].get("timeline_months") not in rp.TIMELINES:
        profile["constraints"]["timeline_months"] = 6
    return profile, None


def draft_from_profile(profile):
    """Turn a saved profile back into an editable draft for the review screen."""
    role = profile["current_role"]
    type_map = {d["label"]: d.get("task_type") for d in role.get("task_details", [])}
    return {
        "skills": [dict(s) for s in profile["skills"]],
        "current_role": {
            "title": role.get("title", ""),
            "industry": role.get("industry", ""),
            "years_experience": role.get("years_experience", ""),
            "tasks": list(role.get("tasks", [])),
            "task_type_map": type_map,
        },
    }


# ---------- Session state and navigation ----------
def init_state():
    defaults = {"step": 1, "pid": 0, "draft": None, "source": None, "final_profile": None}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def go(step):
    st.session_state["step"] = step
    st.rerun()


def set_draft(profile, source):
    st.session_state["draft"] = profile
    st.session_state["source"] = source
    st.session_state["pid"] += 1      # new id so old widget states are not reused
    go(2)


def open_results(profile):
    """Save the confirmed profile and continue to step 3."""
    st.session_state["final_profile"] = profile
    st.session_state.setdefault(
        "scenario_pref", sl.normalize_scenario(profile.get("scenario_focus"))[0])
    go(3)


def start_over():
    """Called from a button: clear the profile and return to the start screen."""
    for key in ["draft", "source", "final_profile", "target_role", "role_pick"]:
        st.session_state.pop(key, None)
    st.session_state["pid"] += 1
    st.session_state["step"] = 1


def reachable(i):
    """Can the user jump to step i from the step bar?"""
    if i == 1:
        return True
    if i == 2:
        return st.session_state.get("draft") is not None
    return st.session_state.get("final_profile") is not None


def jump(i):
    """Called from the step bar. Going to Review from later steps edits the saved profile."""
    if i == 2 and st.session_state.get("final_profile") is not None:
        st.session_state["draft"] = draft_from_profile(st.session_state["final_profile"])
        st.session_state["pid"] += 1
    st.session_state["step"] = i


def remember_scenario():
    st.session_state["scenario_pref"] = st.session_state["scenario_radio"]


def remember_batch():
    st.session_state["batch_pref"] = st.session_state["batch_pick"]


@st.cache_data
def batch_choices():
    """[(batch_id, data_date)] oldest to newest, or [] when the trend file cannot be read."""
    try:
        data = sl.load_signals()
    except (FileNotFoundError, ValueError):
        return []
    return [(b["meta"]["batch_id"], b["meta"]["data_date"]) for b in data["batches"]]


def render_header(step):
    theme.hero()
    st.progress(step / len(STEPS))
    fx.render_dock(STEPS, step, reachable, jump)
    fx.bridge([{"n": i, "label": name, "key": f"dock_{i}",
                "enabled": i == step or reachable(i), "current": i == step}
               for i, name in enumerate(STEPS, start=1)])


def _batch_panel(profile, scenario, ids, batch_id):
    """Batch picker plus the 'what changed' list. Returns the chosen batch id."""
    if not ids:
        st.caption("No trend data batches found.")
        return batch_id
    batch_id = st.selectbox(
        "Trend data batch", ids, index=ids.index(batch_id), key="batch_pick",
        format_func=lambda b: b + ("  (latest)" if b == ids[-1] else ""),
        on_change=remember_batch)
    st.caption("Steps 3 to 5 all use this batch. Pick an older batch to see how new "
               "trend data moves your tasks, roles and plan.")
    st.markdown("**Since the previous data batch**")
    sv.render_changes(profile, scenario, batch_id)
    return batch_id


def _trend_line(batch_id):
    info, error = rp.trend_status(batch_id)
    if not info:
        return f"Trend data not available: {error}"
    synthetic = " (synthetic demo data)" if info["is_synthetic"] else ""
    return (f"Trend data: {info['source_name']}{synthetic}, data date {info['data_date']}, "
            f"batch {info['batch_id']}. Estimates, not forecasts.")


def render_data_controls(profile, compact=False):
    """The one set of data controls, shown on steps 3 to 5. Returns (scenario, batch_id).
    Step 3 (compact=False): scenario switch and source line visible, batch panel folded.
    Steps 4 and 5 (compact=True): everything folded into one bar whose title still
    shows the scenario, source, date and the synthetic flag."""
    options = tb.SCENARIOS
    current = st.session_state.get("scenario_pref", "steady")
    ids = [b for b, _ in batch_choices()]
    batch_id = st.session_state.get("batch_pref")
    if batch_id not in ids:
        batch_id = ids[-1] if ids else None

    def scenario_radio():
        return st.radio("AI progress scenario", options, horizontal=True,
                        index=options.index(current), key="scenario_radio",
                        format_func=lambda x: tb.SCENARIO_LABELS[x],
                        on_change=remember_scenario)

    if compact:
        info, _ = rp.trend_status(batch_id)
        source = (f"{info['source_name']}{' (synthetic demo data)' if info['is_synthetic'] else ''}"
                  f", {info['data_date']}") if info else "not available"
        label = f"{tb.SCENARIO_LABELS[current]}  |  Trend data: {source}  |  Estimates"
        with st.expander(label, key="data_bar", icon=":material/tune:"):
            scenario = scenario_radio()
            batch_id = _batch_panel(profile, scenario, ids, batch_id)
            st.caption(_trend_line(batch_id))
    else:
        c1, c2 = st.columns([2, 3], gap="large")
        with c1:
            scenario = scenario_radio()
        with st.expander("Trend data and updates"):
            batch_id = _batch_panel(profile, scenario, ids, batch_id)
        with c2:
            st.caption(_trend_line(batch_id))
    st.session_state["scenario_pref"] = scenario
    st.session_state["batch_pref"] = batch_id
    return scenario, batch_id


def render_step_nav(step, next_label=None):
    """Back / Next buttons at the bottom of steps 3 to 5."""
    st.divider()
    back, _, nxt = st.columns([1, 3, 1.4])
    back.button("Back", key=f"back_{step}", on_click=jump, args=(step - 1,),
                use_container_width=True)
    if next_label:
        nxt.button(next_label, key=f"next_{step}", type="primary", on_click=jump,
                   args=(step + 1,), use_container_width=True)


# ---------- Setup step 1: starting point ----------
START_BOX_HEIGHT = 560   # both start boxes are at least this tall so they line up (no scrolling)


def set_start_mode(mode):
    """Called from a button: switch the left box between 'cv' and 'role'."""
    st.session_state["start_mode"] = mode


def start_box_cv():
    st.markdown("### I have a CV")
    st.caption("Upload it or paste the text. Emails, phone numbers and IC numbers are "
               "removed before the AI reads anything.")
    uploaded_file = st.file_uploader("Upload PDF, DOCX or TXT", type=["pdf", "docx", "txt"])
    pasted_text = st.text_area("Or paste your CV text", height=120)
    if not has_api_key:
        st.warning("CV analysis needs an LLM key (see your .env file). "
                   "You can still press 'I do not have a CV'.")
    col_go, col_switch, _ = st.columns([1, 1.3, 0.7], gap="small")
    analyse = col_go.button("Analyse my CV", type="primary", disabled=not has_api_key)
    col_switch.button("I do not have a CV", on_click=set_start_mode, args=("role",))
    if analyse:
        raw_text = ""
        if uploaded_file:
            raw_text = extract_text(uploaded_file)
        elif pasted_text:
            raw_text = pasted_text
        if not raw_text:
            st.warning("Please upload a file or paste some text first.")
        else:
            with st.spinner("Removing personal data and extracting skills..."):
                data = extract_skills_llm(strip_pii(raw_text))
            if data:
                set_draft(data, "cv_upload")
            else:
                st.error("AI extraction failed. Try again, or press 'I do not have a CV'.")
                with st.expander("Technical details"):
                    st.code(st.session_state.get("last_error", "unknown"))


def start_box_role():
    st.markdown("### I do not have a CV")
    st.caption("Pick the kind of work you do now. We start from a typical profile "
               "for that role and you adjust it in the next step.")
    template_options = {t["display_name"]["en"]: t for t in occupation_templates}
    selected_occ = st.selectbox("Your current occupation", list(template_options.keys()))
    years_exp = st.selectbox("Years of experience", ["0-1", "1-3", "3-5", "5-10", "10+"])
    col_go, col_switch, _ = st.columns([1.6, 1, 0.9], gap="small")
    go_on = col_go.button("Continue with this role", type="primary")
    col_switch.button("I have a CV", on_click=set_start_mode, args=("cv",))
    if go_on:
        tpl = template_options[selected_occ]
        draft_skills = [{
            "name": s["name"],
            "esco_id": s["esco_id"],
            "mapped": True,
            "level": s["default_level"],
            "evidence": "Standard industry expectation",
            "confidence": "medium",
            "user_confirmed": False,
        } for s in tpl["skills"]]
        set_draft({
            "skills": draft_skills,
            "current_role": {
                "title": selected_occ,
                "industry": "General",
                "years_experience": years_exp,
                "tasks": [clean_label(t["label"]["en"]) for t in tpl["tasks"]],
                "task_type_map": {clean_label(t["label"]["en"]): t.get("task_type")
                                  for t in tpl["tasks"]},
            },
        }, "cold_start_template")


def start_box_saved():
    st.markdown("### I have been here before")
    st.caption("Upload the profile file you saved last time to continue where you left "
               "off. The file stays on your device; we do not store it.")
    saved = st.file_uploader("Upload your profile (JSON)", type=["json"], key="saved_profile")
    if st.button("Continue where I left off", disabled=saved is None):
        profile, error = profile_from_upload(saved)
        if error:
            st.error(error)
        else:
            st.session_state["draft"] = draft_from_profile(profile)
            st.session_state["source"] = profile["source"]
            open_results(profile)


def page_start():
    st.markdown(f"<style>.st-key-card_start_left, .st-key-card_start_saved "
                f"{{ min-height: {START_BOX_HEIGHT}px; overflow: visible !important; }}</style>",
                unsafe_allow_html=True)
    st.subheader("Where are you starting from?")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="card_start_left"):
            if st.session_state.get("start_mode", "cv") == "cv":
                start_box_cv()
            else:
                start_box_role()
    with right:
        with st.container(border=True, key="card_start_saved"):
            start_box_saved()


# ---------- Setup step 2: review ----------
TASK_COLS = [5, 4]            # task checkbox | category
SKILL_COLS = [3, 2.2, 3.4]    # skill checkbox | level slider | read-only note
NOTE_HEADERS = {
    "cv_upload": "What our AI found (read-only)",
    "cold_start_template": "Our note (read-only)",
}


def row_columns(spec):
    """Columns whose content is centred vertically (falls back on older Streamlit)."""
    try:
        return st.columns(spec, vertical_alignment="center")
    except TypeError:
        return st.columns(spec)


def column_headers(spec, labels):
    """A small bold header row above a list of widget rows."""
    for col, text in zip(row_columns(spec), labels):
        col.markdown(f"<div style='font-size:0.82rem;font-weight:600;opacity:.75;'>"
                     f"{html.escape(text)}</div>", unsafe_allow_html=True)


def skill_note_html(skill, source):
    """ESCO status, confidence and evidence in one grey read-only box."""
    lines = []
    if skill.get("mapped"):
        lines.append("In the ESCO skill list")
    else:
        lines.append("<b>Not in the ESCO list</b>, so not used for matching")
    evidence = str(skill.get("evidence", "")).strip()
    conf = str(skill.get("confidence", "")).strip()
    if evidence == "Added by you":
        lines.append("Added by you")
    elif source == "cv_upload":
        lines.append(f"AI confidence: {html.escape(conf or 'unknown')}")
        if evidence:
            lines.append(f"<i>From your CV: &quot;{html.escape(evidence)}&quot;</i>")
    elif source == "cold_start_template":
        lines.append("Typical skill for this role, not from a CV")
    else:
        if conf:
            lines.append(f"Confidence: {html.escape(conf)}")
        if evidence:
            lines.append(f"<i>{html.escape(evidence)}</i>")
    return ("<div style='background:#FAFAFA;border:1px solid #EAEAEA;"
            "border-radius:6px;padding:6px 10px;font-size:0.8rem;line-height:1.45;"
            "color:#666666;'>" + "<br>".join(lines) + "</div>")


def page_review():
    draft = st.session_state["draft"]
    pid = st.session_state["pid"]
    role = draft["current_role"]
    skills = draft["skills"]
    editing = st.session_state.get("final_profile") is not None
    source = st.session_state.get("source")

    st.subheader("Check your skills and tasks")
    source_text = {"cv_upload": "your CV",
                   "cold_start_template": "a typical profile for your role"}.get(source, "your saved profile")
    st.caption(f"Based on {source_text}: **{role.get('title', 'Unknown role')}**. "
               "Your edits decide your results.")

    col_tasks, col_skills = st.columns([5, 8])

    with col_tasks:
        with st.container(border=True, key="card_tasks"):
            st.markdown("#### Daily tasks")
            st.info("Untick tasks you do not do. If our category guess is wrong, change it: "
                    "the category picks the trend data for that task.")
            type_map = role.setdefault("task_type_map", {})
            type_options = [None] + list(sl.TASK_TYPES)
            confirmed_tasks = []
            column_headers(TASK_COLS, ["Task", "Category (our guess)"])
            for i, task in enumerate(role.get("tasks", [])):
                c_task, c_type = row_columns(TASK_COLS)
                with c_task:
                    keep = st.checkbox(task, value=True, key=f"task_{pid}_{i}")
                with c_type:
                    guess = type_map.get(task)
                    chosen = st.selectbox(
                        "Category", type_options,
                        index=type_options.index(guess) if guess in type_options else 0,
                        key=f"task_type_{pid}_{i}", format_func=task_type_label,
                        label_visibility="collapsed")
                type_map[task] = chosen
                if keep:
                    confirmed_tasks.append(task)

    with col_skills:
        with st.container(border=True, key="card_skills"):
            st.markdown("#### Skills")
            st.info("Untick skills you do not have. Slide to set your level: "
                    "1 = beginner, 5 = expert.")
            note_header = NOTE_HEADERS.get(source, "Note (read-only)")
            column_headers(SKILL_COLS, ["Skill (you have it?)", "Your level (1 to 5)",
                                        note_header])
            for i, s in enumerate(skills):
                c_name, c_level, c_note = row_columns(SKILL_COLS)
                with c_name:
                    keep = st.checkbox(s["name"], value=s.get("_keep", True),
                                       key=f"skill_keep_{pid}_{i}")
                with c_level:
                    level = st.slider("Level", 1, 5, clamp_level(s.get("level")),
                                      key=f"skill_level_{pid}_{i}", disabled=not keep,
                                      label_visibility="collapsed")
                with c_note:
                    st.markdown(skill_note_html(s, source), unsafe_allow_html=True)
                s["_keep"] = keep
                s["level"] = clamp_level(level, s.get("level", 3))
            st.caption("The notes on the right are for your information only. They are not your "
                       "input; only your ticks and levels change your results.")

            with st.expander("Add a skill I have"):
                have = {s["name"] for s in skills}
                options = sorted(n for n in esco_skill_names if n not in have)
                new_name = st.selectbox("Skill (from the ESCO list)", options, key=f"add_name_{pid}")
                new_level = st.slider("Your level", 1, 5, 3, key=f"add_level_{pid}")
                if st.button("Add skill", key=f"add_btn_{pid}"):
                    skills.append({
                        "name": new_name,
                        "esco_id": esco_skill_names[new_name],
                        "mapped": True,
                        "level": new_level,
                        "evidence": "Added by you",
                        "confidence": "high",
                        "user_confirmed": False,
                    })
                    st.rerun()

    nav_back, _, nav_next = st.columns([1, 3, 1])
    with nav_back:
        if st.button("Cancel" if editing else "Back"):
            go(3 if editing else 1)
    with nav_next:
        if st.button("Save and continue", type="primary"):
            confirmed_skills = []
            for s in skills:
                if s.get("_keep", True):
                    item = {k: v for k, v in s.items() if k != "_keep"}
                    item["user_confirmed"] = True
                    confirmed_skills.append(item)
            if not confirmed_skills:
                st.error("Keep at least one skill to continue.")
                return
            old = st.session_state.get("final_profile") or {}
            now = datetime.now(timezone.utc).isoformat()
            meta = dict(old.get("meta") or {"created_at": now})
            meta["updated_at"] = now
            profile = {
                "source": st.session_state.get("source"),
                "skills": confirmed_skills,
                "current_role": {
                    "title": role.get("title", ""),
                    "industry": role.get("industry", ""),
                    "years_experience": role.get("years_experience", ""),
                    "tasks": confirmed_tasks,
                    "task_details": [
                        {"label": t, "task_type": role.get("task_type_map", {}).get(t)}
                        for t in confirmed_tasks
                    ],
                },
                "goals": old.get("goals", dict(DEFAULT_GOALS)),
                "constraints": old.get("constraints", dict(DEFAULT_CONSTRAINTS)),
                "risk_preference": old.get("risk_preference", "stable"),
                "scenario_focus": old.get("scenario_focus", "both"),
                "meta": meta,
            }
            open_results(profile)


# ---------- Steps 3 to 5 ----------
def page_day(profile, scenario, batch_id):
    sv.render_compass(profile, scenario, batch_id)
    with st.expander("How it works"):
        sv.render_method(profile, scenario, batch_id)


def page_roles(profile, scenario, batch_id):
    rp.render_roles(profile, scenario, batch_id)


def page_plan(profile, scenario, batch_id):
    rp.render_plan(profile, scenario, batch_id, start_over=start_over)


def page_results(step):
    profile = st.session_state["final_profile"]
    st.caption(STEP_INTRO[step])
    scenario, batch_id = render_data_controls(profile, compact=step in (4, 5))
    if step == 3:
        page_day(profile, scenario, batch_id)
        render_step_nav(3, "See matching roles")
    elif step == 4:
        page_roles(profile, scenario, batch_id)
        render_step_nav(4, "See my learning plan")
    else:
        page_plan(profile, scenario, batch_id)
        render_step_nav(5)


def render_footer():
    st.divider()
    st.caption(f"CV skills are extracted with Google Gemini ({LLM_MODEL}) only when you upload "
               "a CV. Matching uses a fixed, explainable formula on ESCO data, not an AI model. "
               "Sources: ESCO (European Commission); trend signals are a synthetic demo dataset. "
               "All results are estimates to support your decision; you decide.")


# ---------- Main ----------
init_state()
if not intro.done():
    intro.render()
    st.stop()
step = st.session_state["step"]

if step in (3, 4, 5) and st.session_state["final_profile"]:
    render_header(step)
    page_results(step)
elif step == 2 and st.session_state["draft"]:
    render_header(2)
    page_review()
elif step == 1:
    render_header(1)
    page_start()
else:
    st.session_state["step"] = 1
    st.rerun()

render_footer()