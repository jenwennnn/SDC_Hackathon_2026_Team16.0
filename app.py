"""
app.py - ShiftHappens: step-by-step flow
  Step 1: choose a starting point (CV or role template)
  Step 2: review and confirm tasks and skills (human in the loop)
  Step 3: see ranked role matches and skill gaps
Data contract: final_profile keeps skills[].esco_id untouched for the matcher.
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

from results_page import render_results

# ---------- Config (secrets come from environment variables, never from code) ----------
load_dotenv()
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
has_api_key = bool(LLM_API_KEY)
if has_api_key:
    import google.generativeai as genai
    genai.configure(api_key=LLM_API_KEY)

st.set_page_config(page_title="ShiftHappens", layout="wide")

STEPS = ["Your background", "Review skills", "Your matches"]
SEED_FILE = "data/esco_skills_seed_v2.json"
TEMPLATE_FILE = "data/occupation_templates.json"


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


def start_over():
    for key in ["draft", "source", "final_profile"]:
        st.session_state[key] = None
    st.session_state["pid"] += 1
    go(1)


def render_header(step):
    st.title("ShiftHappens")
    st.caption("See where your skills can go in the AI era. This tool gives AI-based estimates "
               "to support your decision. You stay in control of your profile and your choices.")
    cols = st.columns(len(STEPS))
    for i, (col, name) in enumerate(zip(cols, STEPS), start=1):
        if i < step:
            col.markdown(f":green[{i}. {name} - done]")
        elif i == step:
            col.markdown(f"**:blue[{i}. {name}]**")
        else:
            col.markdown(f":gray[{i}. {name}]")
    st.progress(step / len(STEPS))


# ---------- Step 1: starting point ----------
def page_start():
    st.subheader("Where are you starting from?")
    left, right = st.columns(2)

    with left:
        with st.container(border=True):
            st.markdown("### I have a CV")
            st.caption("Upload it or paste the text. Emails, phone numbers and IC numbers are "
                       "removed before the AI reads anything.")
            uploaded_file = st.file_uploader("Upload PDF, DOCX or TXT", type=["pdf", "docx", "txt"])
            pasted_text = st.text_area("Or paste your CV text", height=120)
            if not has_api_key:
                st.warning("CV analysis needs an LLM key (see your .env file). "
                           "You can still start from a role on the right.")
            if st.button("Analyse my CV", type="primary", disabled=not has_api_key):
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
                        st.error("AI extraction failed. Try again, or start from a role on the right.")
                        with st.expander("Technical details"):
                            st.code(st.session_state.get("last_error", "unknown"))

    with right:
        with st.container(border=True):
            st.markdown("### I do not have a CV")
            st.caption("Pick the kind of work you do now. We start from a typical profile "
                       "for that role and you adjust it in the next step.")
            template_options = {t["display_name"]["en"]: t for t in occupation_templates}
            selected_occ = st.selectbox("Your current occupation", list(template_options.keys()))
            years_exp = st.selectbox("Years of experience", ["0-1", "1-3", "3-5", "5-10", "10+"])
            if st.button("Continue with this role", type="primary"):
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
                    },
                }, "cold_start_template")


# ---------- Step 2: review ----------
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

    st.subheader("Check what we found")
    source_text = "your CV" if st.session_state["source"] == "cv_upload" else "a typical profile for your role"
    st.caption(f"Based on {source_text}: **{role.get('title', 'Unknown role')}**. "
               "Fix anything that is wrong. Your edits decide your matches.")

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
            st.caption("Set your level (1 = beginner, 5 = expert) and untick skills you do not have. "
                       "Skills marked 'not in ESCO' cannot be used for matching.")
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
        if st.button("Back"):
            go(1)
    with nav_next:
        if st.button("See my matches", type="primary"):
            apply_edits(skills, edited)
            confirmed_skills = []
            for s in skills:
                if s.get("_keep", True):
                    item = {k: v for k, v in s.items() if k != "_keep"}
                    item["user_confirmed"] = True
                    confirmed_skills.append(item)
            if not confirmed_skills:
                st.error("Keep at least one skill to see matches.")
            else:
                st.session_state["final_profile"] = {
                    "source": st.session_state["source"],
                    "skills": confirmed_skills,
                    "current_role": {
                        "title": role.get("title", ""),
                        "industry": role.get("industry", ""),
                        "years_experience": role.get("years_experience", ""),
                        "tasks": confirmed_tasks,
                    },
                    "goals": {"mode": "undecided", "interests": [], "sdg_importance": 0.3},
                    "constraints": {"hours_per_week": 5, "budget": "free",
                                    "timeline_months": 6, "language": "en"},
                    "risk_preference": "stable",
                    "scenario_focus": "both",
                    "meta": {"created_at": datetime.now(timezone.utc).isoformat()},
                }
                go(3)


# ---------- Step 3: results ----------
def page_results():
    profile = st.session_state["final_profile"]

    bar_info, bar_edit, bar_reset = st.columns([4, 1, 1])
    with bar_info:
        st.caption(f"Profile: {profile['current_role']['title']} | "
                   f"{len(profile['skills'])} skills | {len(profile['current_role']['tasks'])} tasks")
    with bar_edit:
        if st.button("Edit my skills"):
            go(2)
    with bar_reset:
        if st.button("Start over"):
            start_over()

    tab_matches, tab_profile = st.tabs(["Role matches", "My profile data"])
    with tab_matches:
        render_results(profile)
    with tab_profile:
        st.caption("This is the data used for matching. No name, age, gender or contact details are stored.")
        st.download_button("Download profile (JSON)", data=json.dumps(profile, indent=2),
                           file_name="skills_profile.json")
        with st.expander("Show raw JSON"):
            st.json(profile)


# ---------- Main ----------
init_state()
render_header(st.session_state["step"])

if st.session_state["step"] == 1:
    page_start()
elif st.session_state["step"] == 2 and st.session_state["draft"]:
    page_review()
elif st.session_state["step"] == 3 and st.session_state["final_profile"]:
    page_results()
else:
    st.session_state["step"] = 1
    st.rerun()

st.divider()
st.caption(f"Skills are extracted with Google Gemini ({LLM_MODEL}) only when you upload a CV. "
           "Matching uses a fixed, explainable formula on ESCO data, not an AI model. "
           "Sources: ESCO (European Commission).")
