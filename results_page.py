"""
results_page.py - match results display

Input: profile (the final_profile built by app.py)
Output: draws top-3 role cards, then a detail view for any role the user picks.
Usage (inside app.py):
    from results_page import render_results
    render_results(st.session_state['final_profile'])
"""
import json

import pandas as pd
import streamlit as st
from matcher import load_roles, match_roles


@st.cache_data
def _roles():
    return load_roles()


@st.cache_data
def _sdg():
    with open("data/sdg_mapping.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _sdg_tags(title):
    return _sdg()["roles"].get(title, [])


def _description(title):
    for r in _roles():
        if r["title"] == title:
            return r.get("description", "")
    return ""


def render_results(profile, trend=None):
    st.subheader("Your role matches")
    st.caption(
        "Roles are ranked by how much your confirmed skills overlap with each role's "
        "requirements in ESCO (the EU skills classification). These are estimates to "
        "support your own decision, not a prediction or a hiring verdict. "
        "A low overlap is normal: it shows how far a role is from where you are today."
    )
    if trend is None:
        st.caption("Trend signals: not connected yet (matches are shown without trend weighting).")

    results = match_roles(profile, _roles(), trend=trend)

    # ---- Top 3 cards ----
    top = results[:3]
    cols = st.columns(len(top))
    for rank, (col, r) in enumerate(zip(cols, top), start=1):
        with col.container(border=True):
            st.caption(f"Rank {rank}")
            st.markdown(f"**{r['title']}**")
            st.metric("Essential skills you meet", f"{r['essential_have']}/{r['essential_total']}")
            st.caption(f"Skill overlap {r['match_score']}%")
            tags = _sdg_tags(r["title"])
            if tags:
                st.caption("SDG: " + ", ".join(f"{t['sdg']} (target {t['target']})" for t in tags))

    # ---- Detail view ----
    st.markdown("#### Explore a role")
    titles = [r["title"] for r in results]
    pick = st.selectbox("Choose a role to see your skill gap", titles, index=0, key="role_pick")
    r = results[titles.index(pick)]

    if r["match_score"] == 0 and r["essential_have"] == 0:
        st.info("No skill overlap yet. This is a longer-term stretch role.")
    st.write(r["explanation"])

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("**Start with these skills**")
            ess_gaps = [g for g in r["gaps"] if g["relation"] == "essential"][:8]
            gaps = ess_gaps or r["gaps"][:8]
            if gaps:
                df = pd.DataFrame([{
                    "Skill": g["name"],
                    "Your level": g["your_level"],
                    "Role needs": g["required_level"],
                } for g in gaps])
                st.dataframe(df, hide_index=True)
            else:
                st.write("No gaps. You meet every skill for this role.")
    with right:
        with st.container(border=True):
            st.markdown("**Skills you already have**")
            if r["matched"]:
                st.write(", ".join(m["name"] for m in r["matched"][:12]))
            else:
                st.write("None of this role's skills are fully covered yet.")

    # ---- SDG section ----
    with st.container(border=True):
        st.markdown("**Sustainable Development Goals**")
        tags = _sdg_tags(r["title"])
        if tags:
            for t in tags:
                st.write(f"**SDG {t['sdg']}: {t['sdg_name']}** - target {t['target']} "
                         f"({t['link_strength']} link)")
                st.caption(f"Target: {t['target_summary']} Why this role: {t['why']}")
        else:
            st.write("No SDG link recorded for this role yet.")
        pw = _sdg()["pathway_sdgs"]
        st.caption("Following a reskilling plan also supports " +
                   " and ".join(f"SDG {p['sdg']} (target {p['target']}: {p['target_summary'].rstrip('.').lower()})"
                                for p in pw) + ".")
        st.caption("SDG links are a team mapping and are estimates. Source: UN Sustainable Development Goals, "
                   "https://sdgs.un.org/goals")

    desc = _description(r["title"])
    if desc:
        with st.expander("About this role (from ESCO)"):
            st.write(desc)

    st.caption(
        "Required levels are a team assumption (essential = 3, optional = 2); "
        "ESCO does not publish proficiency levels. "
        f"Source: ESCO, [{r['title']}]({r['source']['url']})"
    )