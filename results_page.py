"""
results_page.py - dashboard pages that use matching results

Pages (called from app.py, one per sidebar item):
    render_overview(profile, scenario)  - key numbers, your day, top matches, what changed
    render_roles(profile, scenario)     - all roles ranked, detail and skill gap for one role
    render_plan(profile, scenario)      - learning plan for your target role, SDG links

Trend: trend signals (data/signals.json) are turned into per-skill outlook scores
by trend_bridge.py and fed into the matcher. The scenario ('steady' or 'rapid')
comes from the one global switch in the sidebar.
Target role: the user can pin one role (st.session_state['target_role']); the
learning plan and the Overview follow it. Default = best match.
"""
import json

import pandas as pd
import streamlit as st

import signals_logic as sl
import signals_views as sv
import trend_bridge as tb
from matcher import load_roles, match_roles
from pathway import build_pathway, load_courses

BUDGETS = ["free", "low_cost", "hrd_corp_claimable"]
BUDGET_LABELS = {"free": "Free only", "low_cost": "Low cost",
                 "hrd_corp_claimable": "HRD Corp claimable"}
TIMELINES = [3, 6, 12]


# ---------------------------- cached data ----------------------------

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


# ------------------------------ helpers ------------------------------

def trend_status():
    """(info dict or None, error text or None) for the sidebar."""
    trends, info = _trend_inputs()
    return (info, None) if trends is not None else (None, info)


def compute_matches(profile, scenario):
    """Return (results, trend_used). trend_used is None when signals are unavailable."""
    trends, _ = _trend_inputs()
    if trends is None:
        return match_roles(profile, _roles()), None
    trend = trends[scenario]
    return match_roles(profile, _roles(), trend=trend), trend


def _outlook_text(value):
    if value is None:
        return "no trend data"
    return f"{tb.trend_label(value)} ({value:+.2f})"


def _sdg_tags(title):
    return _sdg().get("roles", {}).get(title, [])


def _description(title):
    for r in _roles():
        if r["title"] == title:
            return r.get("description", "")
    return ""


def target_title(results):
    titles = [r["title"] for r in results]
    pinned = st.session_state.get("target_role")
    return pinned if pinned in titles else titles[0]


def _set_target(title):
    st.session_state["target_role"] = title


def _open_role(title):
    st.session_state["nav"] = "Roles"
    st.session_state["role_pick"] = title


def _open_page(page):
    st.session_state["nav"] = page


def _plan(profile, role_result):
    courses = _courses()
    if not courses:
        return None
    return build_pathway(role_result, profile.get("constraints", {}), courses)


def _trend_caption(trend):
    _, info = _trend_inputs()
    if trend is None:
        st.caption(f"Trend signals not available ({info}). Shown without trend weighting.")
        return
    synthetic = " | synthetic demo data" if info["is_synthetic"] else ""
    st.caption(f"Trend source: {info['source_name']} | data date {info['data_date']}{synthetic}. "
               "Skills with a better outlook count more. Estimates, not forecasts.")


# ------------------------------ Overview ------------------------------

def render_overview(profile, scenario):
    results, trend = compute_matches(profile, scenario)
    by_title = {r["title"]: r for r in results}
    target = by_title[target_title(results)]
    plan = _plan(profile, target)
    day = sv.day_counts(profile, scenario)

    st.caption(f"Scenario: {tb.SCENARIO_LABELS[scenario]}. Change it in the sidebar.")

    # ---- key numbers ----
    k1, k2, k3, k4 = st.columns(4)
    with k1.container(border=True):
        st.metric("Tasks at high AI impact",
                  f"{day['high']} of {day['total']}" if day else "-")
    with k2.container(border=True):
        st.metric("Essential skills met", f"{target['essential_have']}/{target['essential_total']}")
    with k3.container(border=True):
        st.metric("Gaps your plan covers",
                  f"{plan['covered_count']}/{plan['target_count']}"
                  if plan and plan.get("target_count") else "-")
    with k4.container(border=True):
        st.metric("Estimated study time",
                  f"{plan['total_weeks']} wk" if plan and plan["steps"] else "-")
    pinned = st.session_state.get("target_role") in by_title
    st.caption(f"Numbers for your target role: **{target['title']}**"
               + ("" if pinned else " (your best match; pin another role under Roles)") + ".")

    # ---- your day + top matches ----
    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("**Your day at a glance**")
            sv.render_day_summary(profile, scenario)
            st.button("Open My day", key="ov_open_day", on_click=_open_page, args=("My day",))
    with right:
        with st.container(border=True):
            st.markdown("**Top matches**")
            for i, r in enumerate(results[:3], start=1):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"{i}. **{r['title']}**")
                    outlook = (f" | outlook {_outlook_text(r['trend_outlook'])}"
                               if trend is not None else "")
                    st.caption(f"Essential {r['essential_have']}/{r['essential_total']} | "
                               f"overlap {r['match_score']}%{outlook}")
                with c2:
                    st.button("View", key=f"ov_view_{i}", on_click=_open_role, args=(r["title"],))

    # ---- what changed ----
    with st.container(border=True):
        st.markdown("**Since the last data update**")
        sv.render_changes(profile, scenario)

    st.caption("ShiftHappens gives estimates to support your own decisions. "
               "You stay in control of your profile and your choices.")


# ------------------------------ Roles ------------------------------

def _render_scenario_compare(profile):
    trends, _ = _trend_inputs()
    base = {r["title"]: r for r in match_roles(profile, _roles())}
    per_scn = {}
    for scn in tb.SCENARIOS:
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


def _render_scenario_method():
    _, info = _trend_inputs()
    st.markdown("**Outlook = demand - AI exposure x replace share**, where "
                "replace share = (1 - augment index) / 2. "
                "Exposure is higher under rapid AI progress, so the outlook drops more for "
                "tasks that AI tends to replace, and less for tasks where AI mostly assists.")
    rows = [{
        "Task type": sv.TASK_TYPE_NAMES.get(r["task_type"], r["task_type"]),
        "Demand": r["demand_index"],
        "Augment (-1 replace, +1 assist)": r["augment_index"],
        "Exposure steady": r["exposure_steady"],
        "Exposure rapid": r["exposure_rapid"],
        "Outlook steady": r["outlook_steady"],
        "Outlook rapid": r["outlook_rapid"],
    } for r in info["outlook_table"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption(f"Each ESCO skill takes the outlook of its task type, using a team mapping "
               f"({info['mapped_count']} of {info['skill_count']} skills mapped, status: "
               f"{info['skill_map_status']}). Unmapped skills get no trend adjustment. "
               "The formula is a team assumption.")


def render_roles(profile, scenario):
    results, trend = compute_matches(profile, scenario)
    titles = [r["title"] for r in results]
    target = target_title(results)

    st.caption("Roles ranked by how much your confirmed skills overlap with each role's "
               "requirements in ESCO (the EU skills classification). A low overlap is normal: "
               "it shows how far a role is from where you are today.")
    _trend_caption(trend)

    st.dataframe(pd.DataFrame([{
        "Rank": i,
        "Role": r["title"] + ("  (target)" if r["title"] == target else ""),
        "Essential skills met": f"{r['essential_have']}/{r['essential_total']}",
        "Skill overlap %": r["match_score"],
        "Outlook": _outlook_text(r["trend_outlook"]) if trend is not None else "not connected",
    } for i, r in enumerate(results, start=1)]), hide_index=True)

    if st.session_state.get("role_pick") not in titles:
        st.session_state["role_pick"] = target
    pick = st.selectbox("Open a role", titles, key="role_pick")
    r = results[titles.index(pick)]

    with st.container(border=True):
        head, action = st.columns([4, 1])
        with head:
            st.markdown(f"### {r['title']}")
            st.write(r["explanation"])
        with action:
            if st.session_state.get("target_role") == r["title"]:
                st.button("Your target role", key="pin_done", disabled=True)
            else:
                st.button("Set as target", key="pin_role", type="primary",
                          on_click=_set_target, args=(r["title"],))

        m1, m2, m3 = st.columns(3)
        m1.metric("Essential skills met", f"{r['essential_have']}/{r['essential_total']}")
        m2.metric("Skill overlap", f"{r['match_score']}%")
        m3.metric("Role outlook", _outlook_text(r["trend_outlook"]) if trend is not None else "-")

        left, right = st.columns([3, 2])
        with left:
            st.markdown("**Start with these skills**")
            ess_gaps = [g for g in r["gaps"] if g["relation"] == "essential"][:8]
            gaps = ess_gaps or r["gaps"][:8]
            if gaps:
                st.dataframe(pd.DataFrame([{
                    "Skill": g["name"],
                    "Your level": g["your_level"],
                    "Role needs": g["required_level"],
                    "Outlook": _outlook_text(g.get("trend")) if trend is not None else "not connected",
                } for g in gaps]), hide_index=True)
                if trend is not None:
                    st.caption("Order: biggest gap first, with better-outlook skills moved up.")
            else:
                st.write("No gaps. You meet every skill for this role.")
        with right:
            st.markdown("**Skills you already have**")
            if r["matched"]:
                st.write(", ".join(m["name"] for m in r["matched"][:12]))
            else:
                st.write("None of this role's skills are fully covered yet.")

        tags = _sdg_tags(r["title"])
        if tags:
            st.caption("SDG: " + ", ".join(f"SDG {t['sdg']} (target {t['target']}, "
                                            f"{t['link_strength']} link)" for t in tags))

    if trend is not None:
        with st.expander("Compare scenarios: how trend changes your ranking"):
            _render_scenario_compare(profile)
        with st.expander("How the scenarios work"):
            _render_scenario_method()
    desc = _description(r["title"])
    if desc:
        with st.expander("About this role (from ESCO)"):
            st.write(desc)

    st.caption("Required levels are a team assumption (essential = 3, optional = 2); "
               "ESCO does not publish proficiency levels. "
               f"Source: ESCO, [{r['title']}]({r['source']['url']})")


# ------------------------------ Learning plan ------------------------------

def render_plan(profile, scenario):
    results, _ = compute_matches(profile, scenario)
    titles = [r["title"] for r in results]
    target = target_title(results)

    courses = _courses()
    if not courses:
        st.info("No verified course data found yet (data/courses.json). "
                "The plan appears here once courses are added.")
        return

    cons = profile.get("constraints", {})
    c0, c1, c2, c3 = st.columns([2, 1, 1, 1])
    with c0:
        pick = st.selectbox("Plan for role", titles, index=titles.index(target), key="plan_role")
    with c1:
        hours = st.slider("Hours per week", 1, 20, int(cons.get("hours_per_week", 5)), key="plan_hours")
    with c2:
        budget = st.selectbox("Budget", BUDGETS, index=BUDGETS.index(cons.get("budget", "free")),
                              format_func=lambda x: BUDGET_LABELS[x], key="plan_budget")
    with c3:
        months = st.selectbox("Timeline (months)", TIMELINES,
                              index=TIMELINES.index(cons.get("timeline_months", 6)), key="plan_months")
    profile["constraints"] = {**cons, "hours_per_week": hours, "budget": budget,
                              "timeline_months": months}
    if pick != target:
        st.button(f"Set {pick} as my target role", key="plan_pin",
                  on_click=_set_target, args=(pick,))

    r = results[titles.index(pick)]
    plan = build_pathway(r, profile["constraints"], courses)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Gaps covered", f"{plan['covered_count']}/{plan['target_count']}")
    m2.metric("Total study time", f"{plan['total_hours']:g} h")
    m3.metric("Estimated duration",
              f"{plan['total_weeks']} week" + ("" if plan["total_weeks"] == 1 else "s"))
    m4.metric("Estimated cost", f"RM {plan['total_cost_myr']:g}")

    if plan["steps"]:
        if plan["within_timeline"]:
            st.info(f"The listed courses fit your {months}-month target, but they cover only "
                    f"{plan['covered_count']} of {plan['target_count']} essential skill gaps "
                    "for this role. The other gaps have no checked course yet.")
        else:
            st.warning(f"This plan needs about {plan['total_weeks']} weeks, more than your "
                       f"{months}-month target (about {plan['timeline_weeks']} weeks). "
                       "Try more hours per week or a longer timeline.")
        st.dataframe(pd.DataFrame([{
            "Step": p["order"],
            "Course": p["title"],
            "Provider": p["provider"],
            "Teaches (your gaps)": ", ".join(p["covers"]),
            "Hours": p["duration_hours"],
            "Weeks": f"{p['start_week']}-{p['end_week']}",
            "Cost": "Free" if not p["cost_myr"] else f"RM {p['cost_myr']:g}",
            "Language": p["language"],
            "Link": p["url"],
        } for p in plan["steps"]]), hide_index=True,
            column_config={"Link": st.column_config.LinkColumn("Link", display_text="Open")})
    else:
        st.info("None of the courses we have checked cover this role's skill gaps within your budget.")

    if plan["uncovered"]:
        with st.expander(f"{len(plan['uncovered'])} essential skills have no course in our list yet"):
            st.write(", ".join(g["name"] for g in plan["uncovered"][:30]))
            st.caption("We only list courses that a team member has opened and checked by hand.")
    st.caption("Estimates, not guarantees. " + " ".join(plan["assumptions"][:2]))
    st.caption("You decide what to study and when. These are suggestions based on the sources shown.")

    # ---- SDG ----
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
        pw = _sdg().get("pathway_sdgs", [])
        if pw:
            st.caption("Following a reskilling plan also supports " +
                       " and ".join(f"SDG {p['sdg']} (target {p['target']}: "
                                    f"{p['target_summary'].rstrip('.').lower()})" for p in pw) + ".")
        st.caption("SDG links are a team mapping and are estimates. Source: UN Sustainable "
                   "Development Goals, https://sdgs.un.org/goals")