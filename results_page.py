"""
results_page.py - match results display

Input: profile (the final_profile built by app.py)
Output: draws top-3 role cards, then a detail view for any role the user picks.
Trend: trend signals (data/signals.json) are turned into per-skill scores via
trend_bridge.py and fed into the matcher. The user picks an AI progress
scenario (steady / rapid). Each scenario uses its own AI exposure values from
the signal data, so skills that AI is likely to replace lose more weight
under rapid progress (formula in trend_bridge.py).
Usage (inside app.py):
    from results_page import render_results
    render_results(st.session_state['final_profile'])
"""
import json

import pandas as pd
import streamlit as st
import signals_logic as sl
import trend_bridge as tb
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


@st.cache_data
def _trend_inputs():
    """Return ({scenario: trend}, info) from the latest batch, or (None, error text)."""
    try:
        signals = sl.load_signals()
        skill_map = tb.load_skill_map()
    except FileNotFoundError as e:
        return None, f"Trend data file missing: {e.filename}"
    except ValueError as e:
        return None, str(e)
    info = tb.trend_info(signals)
    info["skill_map_status"] = skill_map.get("status", "")
    info["mapped_count"] = skill_map.get("mapped_count", 0)
    info["skill_count"] = skill_map.get("skill_count", 0)
    info["outlook_table"] = tb.outlook_table(signals)
    return tb.build_trends(signals, skill_map), info


def _outlook_text(value):
    if value is None:
        return "no trend data"
    return f"{tb.trend_label(value)} ({value:+.2f})"


def _render_trend_box(info, scenario):
    synthetic = " Synthetic demo data: values are invented, not real statistics." if info["is_synthetic"] else ""
    st.info(
        f"**Trend signals connected** | Source: {info['source_name']} | "
        f"Data date: {info['data_date']} (batch {info['batch_id']}).{synthetic}  \n"
        f"Scenario: **{tb.SCENARIO_LABELS[scenario]}**. Each skill gets an outlook: market "
        f"demand minus the share of the task AI is likely to replace in this scenario. "
        f"Skills with a better outlook count more in your overlap score. "
        "This is an estimate to explore uncertainty, not a forecast."
    )


def _render_scenario_method(info):
    """Show the inputs and the outlook per task type, so the method is checkable."""
    names = {
        "data_entry": "Data entry", "document_processing": "Document handling",
        "customer_communication": "Customer communication",
        "internal_communication": "Internal communication",
        "scheduling_coordination": "Scheduling and coordination",
        "reporting_writing": "Reports and writing",
        "calculation_reconciliation": "Calculation and checking",
        "data_analysis": "Data analysis", "content_creation": "Content creation",
        "physical_or_manual": "Hands-on or manual work",
        "decision_judgement": "Judgement and decisions",
        "relationship_building": "Relationship building",
    }
    st.markdown("**Outlook = demand - AI exposure x replace share**, where "
                "replace share = (1 - augment index) / 2. "
                "Exposure is higher under rapid AI progress, so the outlook drops more for "
                "tasks that AI tends to replace, and less for tasks where AI mostly assists.")
    rows = [{
        "Task type": names.get(r["task_type"], r["task_type"]),
        "Demand": r["demand_index"],
        "Augment (-1 replace, +1 assist)": r["augment_index"],
        "Exposure steady": r["exposure_steady"],
        "Exposure rapid": r["exposure_rapid"],
        "Outlook steady": r["outlook_steady"],
        "Outlook rapid": r["outlook_rapid"],
    } for r in info["outlook_table"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption("All inputs come from the signal data shown above. The formula is a team "
               "assumption. Each skill takes the outlook of its task type.")


def _render_scenario_compare(profile, trends):
    """Same roles under no trend, steady and rapid, so the user sees what changes."""
    base = {r["title"]: r for r in match_roles(profile, _roles())}
    per_scn = {}
    for scn in ("steady", "rapid"):
        res = match_roles(profile, _roles(), trend=trends[scn])
        per_scn[scn] = {r["title"]: (i + 1, r) for i, r in enumerate(res)}
    rows = []
    for title, (rank_s, r_s) in sorted(per_scn["steady"].items(), key=lambda kv: kv[1][0]):
        rank_r, r_r = per_scn["rapid"][title]
        rows.append({
            "Role": title,
            "Rank (steady)": rank_s,
            "Rank (rapid)": rank_r,
            "Overlap without trend %": base[title]["match_score"],
            "Overlap steady %": r_s["match_score"],
            "Overlap rapid %": r_r["match_score"],
            "Outlook steady": _outlook_text(r_s["trend_outlook"]),
            "Outlook rapid": _outlook_text(r_r["trend_outlook"]),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption("Role outlook = average outlook of the role's skills that have trend data. "
               "It is shown for context and does not change the ranking by itself.")


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
    info = None
    if trend is None:
        trends, info = _trend_inputs()
    else:
        trends = {"steady": trend, "rapid": trend}   # one trend given from outside

    scenario = "steady"
    if trends is None:
        st.warning(f"Trend signals not available ({info}). Matches are shown without trend weighting.")
        results = match_roles(profile, _roles())
    else:
        default_scn = sl.normalize_scenario(profile.get("scenario_focus", "both"))[0]
        scenario = st.radio(
            "AI progress scenario", ["steady", "rapid"], horizontal=True, key="match_scenario",
            index=["steady", "rapid"].index(default_scn),
            format_func=lambda x: tb.SCENARIO_LABELS[x])
        if isinstance(info, dict):
            _render_trend_box(info, scenario)
        trend = trends[scenario]
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
            if trend is not None:
                st.caption(f"Role outlook: {_outlook_text(r['trend_outlook'])}")
            tags = _sdg_tags(r["title"])
            if tags:
                st.caption("SDG: " + ", ".join(f"{t['sdg']} (target {t['target']})" for t in tags))

    if trend is not None:
        with st.expander("Compare scenarios: how trend changes your ranking"):
            _render_scenario_compare(profile, trends)
        if isinstance(info, dict):
            with st.expander("How the scenarios work"):
                _render_scenario_method(info)

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
                    "Outlook": _outlook_text(g.get("trend")) if trend is not None else "not connected",
                } for g in gaps])
                st.dataframe(df, hide_index=True)
                if trend is not None:
                    st.caption("Order: biggest gap first, with better-outlook skills moved up.")
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
                st.info(f"The listed courses fit your {months}-month target, but they cover only "
                        f"{plan['covered_count']} of {plan['target_count']} essential skill gaps "
                        f"for this role. The other gaps have no checked course yet.")
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

    if isinstance(info, dict):
        st.caption(
            f"Trend per skill comes from a team mapping of ESCO skills to task types "
            f"({info['mapped_count']} of {info['skill_count']} skills mapped, status: "
            f"{info['skill_map_status']}). Unmapped skills get no trend adjustment. "
            f"The scenario outlook formula is a team assumption.")
    st.caption(
        "Required levels are a team assumption (essential = 3, optional = 2); "
        "ESCO does not publish proficiency levels. "
        f"Source: ESCO, [{r['title']}]({r['source']['url']})"
    )