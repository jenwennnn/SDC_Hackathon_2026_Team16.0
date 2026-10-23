import streamlit as st
import json
import re
import os
from io import StringIO
import PyPDF2
import docx
from openai import OpenAI
from thefuzz import process

# --- SETUP & DATA LOADING ---
st.set_page_config(page_title="Future Skills Intake", layout="centered")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "mock-key-for-ui-testing"))

@st.cache_data
def load_data():
    with open("data/esco_skills_seed.json", "r") as f:
        esco_data = json.load(f)["skills"]
    with open("data/occupation_templates.json", "r") as f:
        templates = json.load(f)["templates"]
    return esco_data, templates

try:
    esco_skills, occupation_templates = load_data()
    esco_skill_names = {s["name"]: s["esco_id"] for s in esco_skills}
except FileNotFoundError:
    st.error("Missing data files. Ensure data/esco_skills_seed.json and data/occupation_templates.json exist.")
    st.stop()

# --- UTILITIES ---
def strip_pii(text):
    # Strip basic emails, phones, and Malaysian ICs (YYMMDD-XX-XXXX)
    text = re.sub(r'\S+@\S+', '[EMAIL REMOVED]', text)
    text = re.sub(r'\+?\d{10,12}', '[PHONE REMOVED]', text)
    text = re.sub(r'\d{6}-\d{2}-\d{4}', '[IC REMOVED]', text)
    return text

def extract_text(file):
    if file.name.endswith('.pdf'):
        reader = PyPDF2.PdfReader(file)
        return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
    elif file.name.endswith('.docx'):
        doc = docx.Document(file)
        return " ".join([para.text for para in doc.paragraphs])
    else:
        return StringIO(file.getvalue().decode("utf-8")).read()

def match_esco_skill(skill_name):
    # Fuzzy match against local ESCO seed
    best_match, score = process.extractOne(skill_name, list(esco_skill_names.keys()))
    if score >= 80:
        return esco_skill_names[best_match], True, best_match
    return None, False, skill_name

def extract_skills_llm(text, retries=1):
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
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            data = json.loads(response.choices[0].message.content)
            # Post-process: map to ESCO
            for skill in data.get("skills", []):
                esco_id, mapped, matched_name = match_esco_skill(skill["name"])
                skill["esco_id"] = esco_id
                skill["mapped"] = mapped
                skill["name"] = matched_name if mapped else skill["name"]
                skill["user_confirmed"] = False
            return data
        except Exception as e:
            if attempt == retries:
                return None

# --- UI ---
st.title("Future-Ready Skills Intake")
st.warning("ℹ️ This tool supports your career decisions using AI estimates. You are fully in control of your profile.")

tab1, tab2 = st.tabs(["Path A: I have a CV", "Path B: Cold Start (No CV)"])

# PATH A: CV UPLOAD
with tab1:
    st.subheader("Upload CV or Paste Text")
    uploaded_file = st.file_uploader("Upload PDF, DOCX, or TXT", type=['pdf', 'docx', 'txt'])
    pasted_text = st.text_area("Or paste your CV text here:")
    
    if st.button("Extract Skills (Path A)"):
        raw_text = ""
        if uploaded_file:
            raw_text = extract_text(uploaded_file)
        elif pasted_text:
            raw_text = pasted_text
            
        if raw_text:
            with st.spinner("Stripping PII and extracting skills..."):
                clean_text = strip_pii(raw_text)
                extracted_data = extract_skills_llm(clean_text)
                
                if extracted_data:
                    st.session_state['draft_profile'] = extracted_data
                    st.session_state['source'] = 'cv_upload'
                    st.success("Extraction complete! Please confirm your skills below.")
                else:
                    st.error("AI extraction failed. Please use Path B (Cold Start).")

# PATH B: COLD START
with tab2:
    st.subheader("Select your occupation")
    template_options = {t["display_name"]["en"]: t for t in occupation_templates}
    selected_occ = st.selectbox("Occupation", list(template_options.keys()))
    years_exp = st.selectbox("Years of Experience", ["0-1", "1-3", "3-5", "5-10", "10+"])
    
    if st.button("Load Template (Path B)"):
        tpl = template_options[selected_occ]
        
        draft_skills = []
        for s in tpl["skills"]:
            draft_skills.append({
                "name": s["name"],
                "esco_id": s["esco_id"],
                "mapped": True,
                "level": s["default_level"],
                "evidence": "Standard industry expectation",
                "confidence": "medium",
                "user_confirmed": False
            })
            
        st.session_state['draft_profile'] = {
            "skills": draft_skills,
            "current_role": {
                "title": selected_occ,
                "industry": "General",
                "years_experience": years_exp,
                "tasks": [task["label"]["en"] for task in tpl["tasks"]]
            }
        }
        st.session_state['source'] = 'cold_start_template'

# --- HUMAN IN THE LOOP & CONFIRMATION ---
if 'draft_profile' in st.session_state:
    st.divider()
    st.header("Confirm Your Profile")
    st.write("Review and adjust your daily tasks and skills. Unmapped skills are flagged.")
    
    prof = st.session_state['draft_profile']
    
    # Task Confirmation
    st.subheader("Daily Tasks")
    confirmed_tasks = []
    for t in prof["current_role"]["tasks"]:
        if st.checkbox(t, value=True):
            confirmed_tasks.append(t)
            
    # Skill Confirmation
    st.subheader("Skills")
    confirmed_skills = []
    for i, skill in enumerate(prof["skills"]):
        cols = st.columns([3, 2, 2, 1])
        with cols[0]:
            name = st.text_input(f"Skill {i+1}", skill["name"], key=f"name_{i}")
            if not skill["mapped"]:
                st.caption("⚠️ Unmapped (Not in ESCO)")
            st.caption(f"Evidence: {skill['evidence']} (Conf: {skill['confidence']})")
        with cols[1]:
            level = st.slider("Proficiency", 1, 5, skill["level"], key=f"lvl_{i}")
        with cols[2]:
            keep = st.checkbox("Keep Skill", value=True, key=f"keep_{i}")
            
        if keep:
            skill["name"] = name
            skill["level"] = level
            skill["user_confirmed"] = True
            confirmed_skills.append(skill)
            
    if st.button("Finalise Profile"):
        final_profile = {
            "source": st.session_state['source'],
            "skills": confirmed_skills,
            "current_role": {
                "title": prof["current_role"]["title"],
                "industry": prof["current_role"]["industry"],
                "years_experience": prof["current_role"].get("years_experience", ""),
                "tasks": confirmed_tasks
            },
            "meta": {"language": "en", "created_at": "2026-10-23T20:29:00Z"}
        }
        st.json(final_profile)
        st.download_button("Download JSON", data=json.dumps(final_profile, indent=2), file_name="skills_profile.json")