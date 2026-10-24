"""
app.py - ShiftHappens

A guided journey in five steps:
  1. Your background   - CV, role template, or a saved profile file
  2. Review            - confirm tasks and skills (human in the loop)
  3. Your day          - how AI may affect your daily tasks (trend signals)
  4. Your roles        - future roles that fit, pick a target role
  5. Your plan         - learning plan for the target role, SDG links, save profile
The step bar at the top is clickable, so users can jump back to any step they
have already reached. ONE AI progress scenario switch (steps 3 to 5) is shared
by all steps.

Data contract: final_profile keeps skills[].esco_id untouched for the matcher.
Nothing personal is stored on a server. Users keep their own profile file
(download under My profile, upload on the start screen to come back).
"""
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
from signals_views import render_changes, render_signals_section

# ---------- Config (secrets come from environment variables, never from code) ----------
load_dotenv()
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
has_api_key = bool(LLM_API_KEY)
if has_api_key:
    import google.generativeai as genai
    genai.configure(api_key=LLM_API_KEY)

st.set_page_config(page_title="ShiftHappens", layout="wide")

STEPS = ["Your background", "Review", "Your day", "Your roles", "Your plan"]
STEP_INTRO = {
    3: "How AI may affect the tasks in your working day.",
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


def strip_pii(text):
    """Remove emails, phone numbers and Malaysian IC numbers before text goes to the LLM."""
    text = re.sub(r"\S+@\S+", "[EMAIL REMOVED]", text)
    text = re.sub(r"\d{6}-\d{2}-\d{4}", "[IC REMOVED]", text)
    text = re.sub(r"\+?\d{10,12}", "[PHONE REMOVED]", text)
    return text


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


def render_header(step):
    st.title("ShiftHappens")
    st.caption("See where your skills can go in the AI era. Estimates to support your "
               "decision; you stay in control.")
    cols = st.columns(len(STEPS))
    for i, (col, name) in enumerate(zip(cols, STEPS), start=1):
        label = f"{i}. {name}"
        if i == step:
            col.button(label, key=f"stepbar_{i}", type="primary", use_container_width=True)
        else:
            col.button(label, key=f"stepbar_{i}", use_container_width=True,
                       disabled=not reachable(i), on_click=jump, args=(i,))
    st.progress(step / len(STEPS))


def render_scenario_switch():
    """The one scenario switch, shown on steps 3 to 5."""
    options = tb.SCENARIOS
    current = st.session_state.get("scenario_pref", "steady")
    c1, c2 = st.columns([2, 3])
    with c1:
        scenario = st.radio("AI progress scenario", options, horizontal=True,
                            index=options.index(current), key="scenario_radio",
                            format_func=lambda x: tb.SCENARIO_LABELS[x],
                            on_change=remember_scenario)
    with c2:
        info, error = rp.trend_status()
        if info:
            synthetic = " (synthetic demo data)" if info["is_synthetic"] else ""
            st.caption(f"Two views of the future, both estimates. Trend data: "
                       f"{info['source_name']}{synthetic}, data date {info['data_date']}.")
        else:
            st.caption(f"Trend data not available: {error}")
    st.session_state["scenario_pref"] = scenario
    return scenario


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
START_BOX_HEIGHT = 560   # both start boxes use the same height so they line up


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
    col_go, col_switch, _ = st.columns([1, 1, 1.5], gap="small")
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
    st.subheader("Where are you starting from?")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, height=START_BOX_HEIGHT):
            if st.session_state.get("start_mode", "cv") == "cv":
                start_box_cv()
            else:
                start_box_role()
    with right:
        with st.container(border=True, height=START_BOX_HEIGHT):
            start_box_saved()


# ---------- Setup step 2: review ----------
def apply_edits(skills, edited_df):
    """Copy the table edits (level, keep) back into the draft skill list."""
    for idx, row in edited_df.iterrows():
        skills[idx]["level"] = clamp_level(row["Level"], skills[idx]["level"])
        skills[idx]["_keep"] = bool(row["Keep"])


def page_review():
    draft = st.session_state["draft"]
    pid = st.session_state["pid"]
    role = draft["current_role"]
    skills = draft["skills"]
    editing = st.session_state.get("final_profile") is not None

    st.subheader("Check your skills and tasks")
    source = st.session_state.get("source")
    source_text = {"cv_upload": "your CV",
                   "cold_start_template": "a typical profile for your role"}.get(source, "your saved profile")
    st.caption(f"Based on {source_text}: **{role.get('title', 'Unknown role')}**. "
               "Fix anything that is wrong. Your edits decide your results.")

    col_tasks, col_skills = st.columns([2, 3])

    with col_tasks:
        with st.container(border=True):
            st.markdown("#### Daily tasks")
            st.caption("Untick tasks you do not do.")
            confirmed_tasks = []
            for i, task in enumerate(role.get("tasks", [])):
                if st.checkbox(task, value=True, key=f"task_{pid}_{i}"):
                    confirmed_tasks.append(task)

    with col_skills:
        with st.container(border=True):
            st.markdown("#### Skills")
            st.caption("Set your level (1 = beginner, 5 = expert) and untick skills you do not have.")
            df = pd.DataFrame([{
                "Keep": s.get("_keep", True),
                "Skill": s["name"],
                "Level": clamp_level(s.get("level")),
                "ESCO": "mapped" if s.get("mapped") else "not in ESCO",
                "Confidence": s.get("confidence", ""),
                "Evidence": s.get("evidence", ""),
            } for s in skills])
            edited = st.data_editor(
                df,
                key=f"skills_{pid}_{len(skills)}",
                hide_index=True,
                disabled=["Skill", "ESCO", "Confidence", "Evidence"],
                column_config={
                    "Keep": st.column_config.CheckboxColumn("Keep", width="small"),
                    "Level": st.column_config.NumberColumn("Level (1-5)", min_value=1, max_value=5, step=1),
                },
            )

            with st.expander("Add a skill I have"):
                have = {s["name"] for s in skills}
                options = sorted(n for n in esco_skill_names if n not in have)
                new_name = st.selectbox("Skill (from the ESCO list)", options, key=f"add_name_{pid}")
                new_level = st.slider("Your level", 1, 5, 3, key=f"add_level_{pid}")
                if st.button("Add skill", key=f"add_btn_{pid}"):
                    apply_edits(skills, edited)       # keep edits made so far
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
            apply_edits(skills, edited)
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
def page_day(profile, scenario):
    render_signals_section(profile, scenario)
    with st.expander("Since the last data update"):
        render_changes(profile, scenario)


def page_roles(profile, scenario):
    rp.render_roles(profile, scenario)


def page_plan(profile, scenario):
    rp.render_plan(profile, scenario)
    with st.container(border=True):
        st.markdown("**Save your profile for next time**")
        st.caption("Download your profile file and upload it on the first step next time. "
                   "It holds no name, age, gender or contact details, and we do not store it.")
        meta = profile.get("meta") or {}
        updated = meta.get("updated_at") or meta.get("created_at", "")
        if updated:
            st.caption(f"Last saved change: {updated[:10]}")
        c1, c2, _ = st.columns([1.3, 1.3, 2])
        c1.download_button("Download my profile (JSON)",
                           data=json.dumps(profile, indent=2, ensure_ascii=True),
                           file_name="shifthappens_profile.json")
        c2.button("Start over", on_click=start_over)
        with st.expander("Show raw profile data"):
            st.json(profile)


def page_results(step):
    profile = st.session_state["final_profile"]
    st.caption(STEP_INTRO[step])
    scenario = render_scenario_switch()
    if step == 3:
        page_day(profile, scenario)
        render_step_nav(3, "See matching roles")
    elif step == 4:
        page_roles(profile, scenario)
        render_step_nav(4, "See my learning plan")
    else:
        page_plan(profile, scenario)
        render_step_nav(5)


def render_footer():
    st.divider()
    st.caption(f"CV skills are extracted with Google Gemini ({LLM_MODEL}) only when you upload "
               "a CV. Matching uses a fixed, explainable formula on ESCO data, not an AI model. "
               "Sources: ESCO (European Commission).")


# ---------- Main ----------
init_state()
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