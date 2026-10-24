"""
app.py - ShiftHappens: step-by-step flow (Modern SaaS Aesthetic Edition)
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

# ---------- Config ----------
load_dotenv()
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
has_api_key = bool(LLM_API_KEY)
if has_api_key:
    import google.generativeai as genai
    genai.configure(api_key=LLM_API_KEY)

st.set_page_config(
    page_title="ShiftHappens — AI Career Navigator",
    page_icon="⚡",
    layout="wide"
)

STEPS = ["Your background", "Review skills", "Your matches"]
SEED_FILE = "data/esco_skills_seed_v2.json"
TEMPLATE_FILE = "data/occupation_templates.json"


# ---------- 方案 A: 注入现代 Web / SaaS 极简风格 CSS ----------
def inject_modern_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stMarkdown, .stText {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .stApp {
        background-color: #F8FAFC;
    }

    /* === 消除顶部白边关键代码 === */
    header[data-testid="stHeader"] {
        display: none !important;  /* 隐藏 Streamlit 默认的顶部空白栏 */
    }
    .block-container {
        padding-top: 1rem !important;   /* 顶部间距降到最低 */
        padding-bottom: 2rem !important;
        max-width: 1140px;
    }

    /* 卡片容器样式 */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 16px !important;
        padding: 1.5rem !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px -2px rgba(0, 0, 0, 0.02);
        transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: #CBD5E1 !important;
        box-shadow: 0 12px 24px -4px rgba(15, 23, 42, 0.06) !important;
    }

    /* 主按钮 */
    button[data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
        border: none !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        padding: 0.55rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.28) !important;
        transition: all 0.2s ease !important;
    }
    button[data-testid="baseButton-primary"]:hover {
        transform: translateY(-1.5px) !important;
        box-shadow: 0 6px 18px rgba(37, 99, 235, 0.38) !important;
    }

    /* 次级按钮 */
    button[data-testid="baseButton-secondary"] {
        border-radius: 10px !important;
        border: 1px solid #E2E8F0 !important;
        background: #FFFFFF !important;
        color: #334155 !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    button[data-testid="baseButton-secondary"]:hover {
        background-color: #F1F5F9 !important;
        border-color: #CBD5E1 !important;
        color: #0F172A !important;
    }

    /* 表单控件圆角 */
    div[data-baseweb="select"] > div, 
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div {
        border-radius: 10px !important;
        border-color: #E2E8F0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

inject_modern_css()


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
    text = re.sub(r"\[cite:[^\]]*\]", "", text)
    text = text.replace("[UNSOURCED]", "")
    return text.strip()


def strip_pii(text):
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
        st.session_state["last_error"] = "LLM_API_KEY not found in environment."
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
    st.session_state["pid"] += 1
    go(2)


def start_over():
    for key in ["draft", "source", "final_profile"]:
        st.session_state[key] = None
    st.session_state["pid"] += 1
    go(1)


# ---------- 现代 Web 头部与分步指示器 ----------
def render_header(step):
# Hero Title 区域
    st.markdown("""
        <div style="text-align: center; margin: 0.5rem 0 2rem 0;">
            <h1 style="font-size: 2.4rem; font-weight: 800; color: #0F172A; letter-spacing: -0.03em; margin: 0 0 0.5rem 0;">
                ShiftHappens
            </h1>
        </div>
    """, unsafe_allow_html=True)

    # 现代步骤指示药丸卡片
    step_items = [
        {"num": 1, "name": "Your background", "desc": "Upload CV or role"},
        {"num": 2, "name": "Review skills", "desc": "Human verification"},
        {"num": 3, "name": "Your matches", "desc": "Rankings & gaps"}
    ]
    cols = st.columns(3)
    for idx, (col, item) in enumerate(zip(cols, step_items), start=1):
        with col:
            if idx < step:
                # 已完成：精致绿
                st.markdown(f"""
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 14px;">
                    <div style="width: 26px; height: 26px; border-radius: 50%; background: #16A34A; color: white; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700;">✓</div>
                    <div>
                        <div style="font-size: 0.88rem; font-weight: 700; color: #166534;">{item['name']}</div>
                        <div style="font-size: 0.72rem; color: #15803D;">Done</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            elif idx == step:
                # 当前激活：高亮蓝 + 轻微投影
                st.markdown(f"""
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #FFFFFF; border: 2px solid #2563EB; border-radius: 14px; box-shadow: 0 4px 14px rgba(37,99,235,0.12);">
                    <div style="width: 26px; height: 26px; border-radius: 50%; background: #2563EB; color: white; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700;">{item['num']}</div>
                    <div>
                        <div style="font-size: 0.88rem; font-weight: 700; color: #0F172A;">{item['name']}</div>
                        <div style="font-size: 0.72rem; color: #2563EB; font-weight: 600;">{item['desc']}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # 未进行：淡灰色
                st.markdown(f"""
                <div style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 14px; opacity: 0.65;">
                    <div style="width: 26px; height: 26px; border-radius: 50%; background: #E2E8F0; color: #64748B; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700;">{item['num']}</div>
                    <div>
                        <div style="font-size: 0.88rem; font-weight: 600; color: #64748B;">{item['name']}</div>
                        <div style="font-size: 0.72rem; color: #94A3B8;">Pending</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    st.write("")


# ---------- Step 1: starting point ----------
def page_start():
    st.markdown("<h3 style='margin-bottom: 0.2rem; font-weight: 700;'>Where are you starting from?</h3>", unsafe_allow_html=True)
    st.caption("Select how you would like to construct your profile.")
    st.write("")

    left, right = st.columns(2, gap="large")

    with left:
        with st.container(border=True):
            st.markdown("""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <h4 style="margin: 0; font-weight: 700; font-size: 1.15rem;">📄 I have a CV</h4>
                    <span style="font-size: 0.75rem; background: #E0E7FF; color: #3730A3; padding: 2px 8px; border-radius: 6px; font-weight: 600;">AI Powered</span>
                </div>
            """, unsafe_allow_html=True)
            st.caption("Upload or paste text. Contact details and IC numbers are stripped automatically prior to extraction.")
            
            uploaded_file = st.file_uploader("Upload PDF, DOCX or TXT", type=["pdf", "docx", "txt"])
            pasted_text = st.text_area("Or paste your CV text directly", height=120, placeholder="Paste your professional experience here...")
            
            if not has_api_key:
                st.warning("⚠️ CV analysis requires an LLM key in your .env file. You can still use the role template on the right.")
            
            st.write("")
            if st.button("Analyse my CV", type="primary", use_container_width=True, disabled=not has_api_key):
                raw_text = ""
                if uploaded_file:
                    raw_text = extract_text(uploaded_file)
                elif pasted_text:
                    raw_text = pasted_text
                if not raw_text:
                    st.warning("Please upload a file or paste text first.")
                else:
                    with st.spinner("Anonymizing data and structuring skills..."):
                        data = extract_skills_llm(strip_pii(raw_text))
                    if data:
                        set_draft(data, "cv_upload")
                    else:
                        st.error("Extraction failed. Please check technical details or proceed via template.")
                        with st.expander("Technical details"):
                            st.code(st.session_state.get("last_error", "unknown"))

    with right:
        with st.container(border=True):
            st.markdown("""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <h4 style="margin: 0; font-weight: 700; font-size: 1.15rem;">💼 I do not have a CV</h4>
                    <span style="font-size: 0.75rem; background: #F1F5F9; color: #475569; padding: 2px 8px; border-radius: 6px; font-weight: 600;">Instant</span>
                </div>
            """, unsafe_allow_html=True)
            st.caption("Select your current occupation to initialize with an industry-standard skill set, then tailor it.")
            
            template_options = {t["display_name"]["en"]: t for t in occupation_templates}
            selected_occ = st.selectbox("Your current occupation", list(template_options.keys()))
            years_exp = st.selectbox("Years of experience", ["0-1", "1-3", "3-5", "5-10", "10+"])
            
            st.write("")
            st.write("")
            if st.button("Continue with this role", type="primary", use_container_width=True):
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
    for idx, row in edited_df.iterrows():
        skills[idx]["level"] = clamp_level(row["Level"], skills[idx]["level"])
        skills[idx]["_keep"] = bool(row["Keep"])


def page_review():
    draft = st.session_state["draft"]
    pid = st.session_state["pid"]
    role = draft["current_role"]
    skills = draft["skills"]

    st.markdown("<h3 style='margin-bottom: 0.2rem; font-weight: 700;'>Verify & Refine Skills</h3>", unsafe_allow_html=True)
    source_badge = "CV Extraction" if st.session_state["source"] == "cv_upload" else "Role Template"
    st.markdown(f"<span style='color: #64748B;'>Identified profile: <strong>{role.get('title', 'Unknown role')}</strong> · Source: <code>{source_badge}</code></span>", unsafe_allow_html=True)
    st.write("")

    col_tasks, col_skills = st.columns([2, 3], gap="large")

    with col_tasks:
        with st.container(border=True):
            st.markdown("#### 📋 Daily Tasks")
            st.caption("Deselect duties you do not perform in your daily routine:")
            confirmed_tasks = []
            for i, task in enumerate(role.get("tasks", [])):
                if st.checkbox(task, value=True, key=f"task_{pid}_{i}"):
                    confirmed_tasks.append(task)

    with col_skills:
        with st.container(border=True):
            st.markdown("#### 🎯 Core Skills")
            st.caption("Adjust levels (1: Beginner to 5: Expert) and discard inapplicable skills:")
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

            with st.expander("＋ Add missing skill from ESCO taxonomy"):
                have = {s["name"] for s in skills}
                options = sorted(n for n in esco_skill_names if n not in have)
                new_name = st.selectbox("Skill name", options, key=f"add_name_{pid}")
                new_level = st.slider("Your proficiency", 1, 5, 3, key=f"add_level_{pid}")
                if st.button("Add to profile", key=f"add_btn_{pid}"):
                    apply_edits(skills, edited)
                    skills.append({
                        "name": new_name,
                        "esco_id": esco_skill_names[new_name],
                        "mapped": True,
                        "level": new_level,
                        "evidence": "User added manually",
                        "confidence": "high",
                        "user_confirmed": False,
                    })
                    st.rerun()

    st.write("")
    nav_back, _, nav_next = st.columns([1, 2, 1])
    with nav_back:
        if st.button("← Back to Source"):
            go(1)
    with nav_next:
        if st.button("Generate Matches →", type="primary", use_container_width=True):
            apply_edits(skills, edited)
            confirmed_skills = []
            for s in skills:
                if s.get("_keep", True):
                    item = {k: v for k, v in s.items() if k != "_keep"}
                    item["user_confirmed"] = True
                    confirmed_skills.append(item)
            if not confirmed_skills:
                st.error("Please retain at least one valid skill to proceed.")
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

    # Modern Action / Stat bar
    with st.container(border=True):
        bar_info, bar_edit, bar_reset = st.columns([4, 1.2, 1])
        with bar_info:
            st.markdown(f"""
                <div style="font-weight: 700; font-size: 1.1rem; color: #0F172A;">{profile['current_role']['title']}</div>
                <div style="font-size: 0.85rem; color: #64748B;">
                    Verified skills: <strong>{len(profile['skills'])}</strong> · Selected tasks: <strong>{len(profile['current_role']['tasks'])}</strong>
                </div>
            """, unsafe_allow_html=True)
        with bar_edit:
            if st.button("✏️ Edit Profile", use_container_width=True):
                go(2)
        with bar_reset:
            if st.button("🔄 Reset", use_container_width=True):
                start_over()

    st.write("")
    tab_matches, tab_profile = st.tabs(["🎯 Recommended Roles", "📁 My Profile Data"])
    with tab_matches:
        render_results(profile)
    with tab_profile:
        st.caption("Export or review the clean, non-PII dataset used for mathematical ESCO matching.")
        st.download_button("Download profile (JSON)", data=json.dumps(profile, indent=2),
                           file_name="skills_profile.json")
        with st.expander("Inspect JSON payload"):
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
st.markdown("""
    <div style="text-align: center; color: #94A3B8; font-size: 0.8rem; padding: 1rem 0;">
        Powered by Google Gemini 2.5 for text parsing · Deterministic ESCO Framework by European Commission · ShiftHappens v2.0
    </div>
""", unsafe_allow_html=True)