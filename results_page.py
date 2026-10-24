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
from pathway import build_pathway, load_courses


@st.cache_data
def _roles():
    return load_roles()


@st.cache_data
def _courses():
    return load_courses()


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

    # ---- Learning plan ----
    st.markdown("#### Your learning plan")
    courses = _courses()
    if not courses:
        st.info("No verified course data found yet (data/courses.json). "
                "The plan appears here once courses are added.")
    else:
        cons = profile.get("constraints", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            hours = st.slider("Hours per week", 1, 20, int(cons.get("hours_per_week", 5)), key="plan_hours")
        with c2:
            budget = st.selectbox(
                "Budget", ["free", "low_cost", "hrd_corp_claimable"],
                index=["free", "low_cost", "hrd_corp_claimable"].index(cons.get("budget", "free")),
                format_func=lambda x: {"free": "Free only", "low_cost": "Low cost",
                                       "hrd_corp_claimable": "HRD Corp claimable"}[x],
                key="plan_budget")
        with c3:
            months = st.selectbox("Target timeline (months)", [3, 6, 12],
                                  index=[3, 6, 12].index(cons.get("timeline_months", 6)), key="plan_months")
        plan_cons = {**cons, "hours_per_week": hours, "budget": budget, "timeline_months": months}
        profile["constraints"] = plan_cons      # keep the profile in sync with the sliders
        plan = build_pathway(r, plan_cons, courses)

        m1, m2, m3 = st.columns(3)
        m1.metric("Total study time", f"{plan['total_hours']:g} h")
        m2.metric("Estimated duration", f"{plan['total_weeks']} week" + ("" if plan['total_weeks'] == 1 else "s"))
        m3.metric("Estimated cost", f"RM {plan['total_cost_myr']:g}")

        if plan["steps"]:
            if plan["within_timeline"]:
                st.success(f"This plan fits your {months}-month target "
                           f"(covers {plan['covered_count']} of {plan['target_count']} essential skill gaps).")
            else:
                st.warning(f"This plan needs about {plan['total_weeks']} weeks, more than your "
                           f"{months}-month target (about {plan['timeline_weeks']} weeks). "
                           "Try more hours per week or a longer timeline.")
            df_plan = pd.DataFrame([{
                "Step": p["order"],
                "Course": p["title"],
                "Provider": p["provider"],
                "Teaches (your gaps)": ", ".join(p["covers"]),
                "Hours": p["duration_hours"],
                "Weeks": f"{p['start_week']}-{p['end_week']}",
                "Cost": "Free" if not p["cost_myr"] else f"RM {p['cost_myr']:g}",
                "Language": p["language"],
                "Link": p["url"],
            } for p in plan["steps"]])
            st.dataframe(df_plan, hide_index=True,
                         column_config={"Link": st.column_config.LinkColumn("Link", display_text="Open")})
        else:
            st.info("None of the courses we have checked cover this role's skill gaps within your budget.")

        if plan["uncovered"]:
            with st.expander(f"{len(plan['uncovered'])} essential skills have no course in our list yet"):
                st.write(", ".join(g["name"] for g in plan["uncovered"][:30]))
                st.caption("We only list courses that a team member has opened and checked by hand.")
        st.caption("Estimates, not guarantees. " + " ".join(plan["assumptions"][:2]))
        st.caption("You decide what to study and when. These are suggestions based on the sources shown.")

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
