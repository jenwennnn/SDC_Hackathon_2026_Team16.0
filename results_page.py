"""
results_page.py - steps 4 and 5 of the guided journey

Called from app.py:
    render_roles(profile, scenario, batch_id)  - all roles ranked, detail and skill gap for one role
    render_plan(profile, scenario, batch_id)   - learning plan for your target role, SDG links
    compute_matches(profile, scenario, batch_id)
    trend_status(batch_id)

Trend: trend signals (data/signals.json) are turned into per-skill outlook scores
by trend_bridge.py and fed into the matcher. The scenario ('steady' or 'rapid')
and the data batch come from the shared controls in app.py (steps 3 to 5).
batch_id=None means the newest batch.
Step 4 layout: one slider, a clickable ranking (a click opens the role page in a
pop-up), and three equal tool buttons that open pop-ups (fairness, scenarios,
how it works).
Ranking: roles are sorted by future fit (matcher.rank_by_future_fit). The user
sets how much the trend outlook counts with the slider on step 4
(st.session_state['outlook_weight'], 0 to 1); step 5 uses the same value.
Target role: the user can pin one role (st.session_state['target_role']); the
learning plan follows it. Default = best match.
"""
import html
import json

import pandas as pd
import streamlit as st

import signals_logic as sl
import signals_views as sv
import trend_bridge as tb
import fairness
import fx
from matcher import DEFAULT_OUTLOOK_WEIGHT, load_roles, match_roles, rank_by_future_fit
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
def _trend_inputs(batch_id=None):
    """Return ({scenario: trend}, info) for one batch, or (None, error text).
    info also holds the previous batch's trends (or None) for change columns."""
    try:
        signals = sl.load_signals()
        skill_map = tb.load_skill_map()
    except FileNotFoundError as e:
        return None, f"Trend data file missing: {e.filename}"
    except ValueError as e:
        return None, str(e)
    if batch_id not in sl.batch_ids(signals):
        batch_id = tb.latest_batch_id(signals)
    info = tb.trend_info(signals, batch_id)
    info["skill_map_status"] = skill_map.get("status", "")
    info["mapped_count"] = skill_map.get("mapped_count", 0)
    info["skill_count"] = skill_map.get("skill_count", 0)
    info["outlook_table"] = tb.outlook_table(signals, batch_id)
    prev = sl.previous_batch(signals, batch_id)
    if prev is not None:
        info["prev_batch_id"] = prev["meta"]["batch_id"]
        info["prev_trends"] = tb.build_trends(signals, skill_map, info["prev_batch_id"])
    else:
        info["prev_batch_id"] = None
        info["prev_trends"] = None
    return tb.build_trends(signals, skill_map, batch_id), info


# ------------------------------ helpers ------------------------------

def trend_status(batch_id=None):
    """(info dict or None, error text or None) for the shared controls."""
    trends, info = _trend_inputs(batch_id)
    return (info, None) if trends is not None else (None, info)


def outlook_weight():
    return st.session_state.get("outlook_weight", DEFAULT_OUTLOOK_WEIGHT)


def _rank(profile, trend):
    return rank_by_future_fit(match_roles(profile, _roles(), trend=trend), outlook_weight())


def compute_matches(profile, scenario, batch_id=None):
    """Return (results sorted by future fit, trend_used). trend_used is None when signals are unavailable."""
    trends, _ = _trend_inputs(batch_id)
    if trends is None:
        return _rank(profile, None), None
    trend = trends[scenario]
    return _rank(profile, trend), trend


def _previous_ranking(profile, scenario, batch_id):
    """({role title: (rank, outlook)} for the previous batch, previous batch id), or (None, None)."""
    trends, info = _trend_inputs(batch_id)
    if trends is None or not info.get("prev_trends"):
        return None, None
    prev = _rank(profile, info["prev_trends"][scenario])
    return ({r["title"]: (i, r["trend_outlook"]) for i, r in enumerate(prev, start=1)},
            info["prev_batch_id"])


def _rank_change_text(now, before):
    if before is None:
        return "-"
    d = before - now
    if d == 0:
        return "same"
    return f"up {d}" if d > 0 else f"down {-d}"


def _change_text(now, before):
    if now is None or before is None:
        return "-"
    d = round(now - before, 2)
    return "no change" if d == 0 else f"{d:+.2f}"


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


def _trend_caption(trend, batch_id=None):
    _, info = _trend_inputs(batch_id)
    if trend is None:
        st.caption(f"Trend signals not available ({info}). Shown without trend weighting.")
        return
    synthetic = " | synthetic demo data" if info["is_synthetic"] else ""
    st.caption(f"Trend source: {info['source_name']} | data date {info['data_date']}{synthetic}. "
               "Skills with a better outlook count more. Estimates, not forecasts.")


# ------------------------------ Roles ------------------------------

def _render_scenario_compare(profile, batch_id=None):
    trends, _ = _trend_inputs(batch_id)
    base = {r["title"]: r for r in _rank(profile, None)}
    per_scn = {scn: {r["title"]: (i + 1, r) for i, r in enumerate(_rank(profile, trends[scn]))}
               for scn in tb.SCENARIOS}
    rows = []
    for title, (rank_s, r_s) in sorted(per_scn["steady"].items(), key=lambda kv: kv[1][0]):
        rank_r, r_r = per_scn["rapid"][title]
        rows.append({
            "Role": title,
            "Rank (steady)": rank_s,
            "Rank (rapid)": rank_r,
            "Future fit steady": r_s["future_fit"],
            "Future fit rapid": r_r["future_fit"],
            "Outlook steady": _outlook_text(r_s["trend_outlook"]),
            "Outlook rapid": _outlook_text(r_r["trend_outlook"]),
            "Skill overlap % (no trend)": base[title]["match_score"],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption(f"Both columns use your current outlook weight ({round(outlook_weight() * 100)}%). "
               "Roles whose tasks AI tends to replace lose more under rapid AI progress.")


def _render_scenario_method(batch_id=None):
    _, info = _trend_inputs(batch_id)
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


def _remember_weight():
    st.session_state["outlook_weight"] = st.session_state["outlook_weight_pct"] / 100


def _fairness_result(profile, trend):
    return fairness.check_fairness(profile, _roles(), trend, outlook_weight())


def render_fairness(profile, trend):
    """Fairness check content (shown inside its dialog)."""
    result = _fairness_result(profile, trend)
    passed = sum(ok for _, ok in result["tests"])
    status = "passed" if result["passed"] else "FAILED"
    st.markdown(f"**Result: {status} ({passed} of {len(result['tests'])} tests)**")
    st.write("We re-ran your ranking after adding or changing personal details. "
             "The ranking, scores and skill gaps must stay exactly the same, because "
             "only your confirmed skills and levels are used.")
    st.dataframe(pd.DataFrame([{"Changed detail": name,
                                "Results unchanged": "yes" if ok else "NO"}
                               for name, ok in result["tests"]]), hide_index=True)
    stored = ", ".join(result["stored_protected"]) or "none"
    st.caption(f"Protected details stored in your profile: {stored}. "
               "Not covered by this check: bias inside ESCO data or our team mappings, "
               "and how the AI reads a CV (you review every extracted skill before matching).")


def _outlook_word(value):
    if value is None:
        return "No data"
    return tb.trend_label(value).capitalize()


def _render_how_it_works(profile, results, trend, batch_id, prev_rank, prev_id):
    w = round(outlook_weight() * 100)
    st.markdown(f"**Future fit = {100 - w}% skill readiness + {w}% outlook score.**")
    st.write("Skill readiness compares your confirmed skills with each role's skills in ESCO "
             "(the EU skills classification). It is relative: your closest role scores 100. "
             "Outlook score turns the role outlook (-1 to +1) into 0 to 100. Skills with a "
             "better outlook also count more inside the skill comparison.")
    _trend_caption(trend, batch_id)
    rows = []
    for i, r in enumerate(results, start=1):
        row = {"Rank": i, "Role": r["title"], "Future fit": r["future_fit"],
               "Skill readiness": r["readiness"],
               "Skill overlap %": r["match_score"],
               "Essential skills met": f"{r['essential_have']}/{r['essential_total']}",
               "Outlook": _outlook_text(r["trend_outlook"]) if trend is not None else "not connected"}
        if prev_rank is not None:
            _, before_outlook = prev_rank.get(r["title"], (None, None))
            row[f"Outlook change since {prev_id}"] = _change_text(r["trend_outlook"], before_outlook)
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    if trend is not None:
        st.markdown("**How the scenarios work**")
        _render_scenario_method(batch_id)
    st.caption("Required levels are a team assumption (essential = 3, optional = 2); "
               "ESCO does not publish proficiency levels.")


def _show_dialog(title, body, *args):
    """Open a large pop-up window that runs body(*args)."""
    st.dialog(title, width="large")(body)(*args)


def _role_page(r, trend):
    """The pop-up page for one role: its dashboard and the ESCO description."""
    is_target = st.session_state.get("target_role") == r["title"]
    head, action = st.columns([3, 1.2], vertical_alignment="center")
    with head:
        st.write(r["explanation"])
    with action:
        if is_target:
            st.button("Your target role", key="dlg_target_done", disabled=True,
                      icon=":material/flag:", width="stretch")
        elif st.button("Set as my target", key="dlg_set_target", type="primary",
                       icon=":material/flag:", width="stretch"):
            _set_target(r["title"])
            st.rerun()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Essential skills met", f"{r['essential_have']}/{r['essential_total']}")
    m2.metric("Future fit", f"{r['future_fit']:g}")
    m3.metric("Role outlook", _outlook_text(r["trend_outlook"]) if trend is not None else "-")
    m4.metric("Skill overlap", f"{r['match_score']}%")

    left, right = st.columns([3, 2], gap="large")
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
                st.caption("Biggest gap first, with better-outlook skills moved up.")
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
            st.markdown("**SDG link**")
            st.caption(", ".join(f"SDG {t['sdg']} {t['sdg_name']} (target {t['target']}, "
                                 f"{t['link_strength']} link)" for t in tags))

    st.markdown("**About this role (from ESCO)**")
    st.write(_description(r["title"]) or "No description available.")
    st.caption("Required levels are a team assumption (essential = 3, optional = 2); "
               "ESCO does not publish proficiency levels. "
               f"Source: ESCO, [{r['title']}]({r['source']['url']})")


ROW_COLS = [0.5, 3.2, 2.4, 1.3, 1.1, 1.1]   # rank | role | fit | essential | outlook | change


def _open_role(title):
    """Called from a role button: open that role's pop-up page on this run."""
    st.session_state["open_role"] = title


def _fit_bar(value):
    pct = max(0.0, min(100.0, float(value or 0)))
    return (f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<div style="flex:1;height:8px;border-radius:999px;background:#EAEAEA;">'
            f'<div style="width:{pct:.0f}%;height:8px;border-radius:999px;'
            f'background:#171717;"></div></div>'
            f'<span style="min-width:26px;text-align:right;font-weight:600;">{pct:.0f}</span></div>')


def _render_role_list(results, trend, target, prev_rank, prev_id):
    heads = ["Rank", "Role (click to open)", "Future fit", "Essential skills met", "Outlook",
             f"Since {prev_id}" if prev_rank is not None else ""]
    for col, text in zip(st.columns(ROW_COLS, vertical_alignment="center"), heads):
        col.markdown(f"<div style='font-size:0.82rem;font-weight:600;opacity:.75;'>{text}</div>",
                     unsafe_allow_html=True)
    for i, r in enumerate(results, start=1):
        with st.container(key=f"rolerow_{i}"):
            c = st.columns(ROW_COLS, vertical_alignment="center")
            c[0].markdown(f"**{i}**")
            label = r["title"] + ("  (your target)" if r["title"] == target else "")
            c[1].button(label, key=f"open_role_{i}", type="tertiary",
                        icon=":material/open_in_new:", icon_position="right",
                        on_click=_open_role, args=(r["title"],))
            c[2].markdown(_fit_bar(r["future_fit"]), unsafe_allow_html=True)
            c[3].markdown(f"{r['essential_have']}/{r['essential_total']}")
            c[4].markdown(_outlook_word(r["trend_outlook"]) if trend is not None else "-")
            if prev_rank is not None:
                before_rank, _ = prev_rank.get(r["title"], (None, None))
                c[5].markdown(_rank_change_text(i, before_rank))


def render_roles(profile, scenario, batch_id=None):
    st.markdown("#### How much should market trends count in your ranking?")
    st.slider("How much should market trends count in your ranking?", 0, 100,
              value=round(outlook_weight() * 100), step=10, format="%d%%",
              key="outlook_weight_pct", on_change=_remember_weight,
              label_visibility="collapsed")
    st.caption("0% = rank by your current skills only. Higher = roles with growing demand move up.")

    results, trend = compute_matches(profile, scenario, batch_id)
    titles = [r["title"] for r in results]
    target = target_title(results)
    prev_rank, prev_id = _previous_ranking(profile, scenario, batch_id)
    w = round(outlook_weight() * 100)

    with st.container(border=True, key="card_roles"):
        st.markdown("#### Roles that fit you")
        st.info(f"Ranked by future fit: {100 - w}% your skills, {w}% market trend. "
                "Click a role to open its page.")
        _render_role_list(results, trend, target, prev_rank, prev_id)
        st.caption(f"Your target role: {target}. Your learning plan in step 5 follows it. "
                   "Estimates, not forecasts.")

    if st.button("Compare scenarios: how steady vs rapid AI progress changes your ranking",
                 key="tool_compare", icon=":material/compare_arrows:", width="stretch",
                 disabled=trend is None):
        _show_dialog("Compare scenarios", _render_scenario_compare, profile, batch_id)
    c1, c2 = st.columns(2)
    if c1.button("Fairness check", key="tool_fair", icon=":material/balance:", width="stretch"):
        _show_dialog("Fairness check", render_fairness, profile, trend)
    if c2.button("How it works", key="tool_how", icon=":material/functions:", width="stretch"):
        _show_dialog("How it works", _render_how_it_works, profile, results, trend, batch_id,
                     prev_rank, prev_id)

    opened = st.session_state.pop("open_role", None)
    if opened in titles:
        _show_dialog(opened, _role_page, results[titles.index(opened)], trend)


# ------------------------------ Learning plan ------------------------------

def _course_card(p):
    cost = "Free" if not p["cost_myr"] else f"RM {p['cost_myr']:g}"
    url = html.escape(p["url"], quote=True)
    return ('<div class="v-course">'
            f'<div class="v-step">{p["order"]}</div>'
            '<div class="v-course-body">'
            f'<div class="v-course-title"><a href="{url}" target="_blank" rel="noopener">'
            f'{html.escape(p["title"])}</a></div>'
            f'<div class="v-course-meta">{html.escape(p["provider"])} &middot; '
            f'{p["duration_hours"]:g} h &middot; weeks {p["start_week"]}-{p["end_week"]} &middot; '
            f'{cost} &middot; {html.escape(p["language"])}</div>'
            f'<div class="v-course-teaches">Closes: {html.escape(", ".join(p["covers"]))}</div>'
            '</div></div>')


def _sdg_line(title):
    parts = [f"SDG {p['sdg']}.{p['target'].split('.')[-1]}" for p in _sdg().get("pathway_sdgs", [])]
    role = [f"SDG {t['target']}" for t in _sdg_tags(title)]
    text = "This plan supports " + " and ".join(parts) if parts else ""
    if role:
        text += f"; the role links to {', '.join(role)}"
    return text + ". Team mapping, an estimate."


def _plan_details(r, plan):
    """Skills without a course and the plan's assumptions."""
    if plan["uncovered"]:
        st.markdown(f"**{len(plan['uncovered'])} essential skills have no course in our list yet**")
        st.write(", ".join(g["name"] for g in plan["uncovered"][:30]))
        st.caption("We only list courses that a team member has opened and checked by hand.")
    st.markdown("**Assumptions**")
    for a in plan["assumptions"]:
        st.markdown(f"- {a}")


def _sdg_details(r):
    """SDG links of the role and of reskilling itself."""
    st.markdown(f"**This role: {r['title']}**")
    tags = _sdg_tags(r["title"])
    if tags:
        for t in tags:
            st.write(f"SDG {t['sdg']}: {t['sdg_name']} - target {t['target']} "
                     f"({t['link_strength']} link)")
            st.caption(f"Target: {t['target_summary']} Why this role: {t['why']}")
    else:
        st.write("No SDG link recorded for this role yet.")
    st.markdown("**Following a reskilling plan**")
    for p in _sdg().get("pathway_sdgs", []):
        st.write(f"SDG {p['sdg']}: {p['sdg_name']} - target {p['target']} ({p['link_strength']} link)")
        st.caption(f"Target: {p['target_summary']} Why: {p['why']}")
    st.caption("SDG links are a team mapping and are estimates. Source: UN Sustainable "
               "Development Goals, https://sdgs.un.org/goals")



def _raw_profile(profile):
    st.caption("This is everything your profile file holds. No name, age, gender or "
               "contact details.")
    st.json(profile)


def render_plan(profile, scenario, batch_id=None, start_over=None):
    results, _ = compute_matches(profile, scenario, batch_id)
    titles = [r["title"] for r in results]
    target = target_title(results)

    courses = _courses()
    if not courses:
        st.info("No verified course data found yet (data/courses.json). "
                "The plan appears here once courses are added.")
        return

    if st.session_state.get("plan_role") not in titles:
        st.session_state["plan_role"] = target
    with st.container(key="card_plan_role"):
        head, choose, pin = st.columns([1.5, 2.6, 1.2], vertical_alignment="center")
        head.markdown("#### Your learning plan for")
        with choose:
            pick = st.selectbox("Plan for role", titles, key="plan_role",
                                format_func=lambda t: t + ("  (your target)" if t == target else ""),
                                label_visibility="collapsed")
        with pin:
            if pick != target:
                st.button("Set as my target", key="plan_pin", icon=":material/flag:",
                          width="stretch", on_click=_set_target, args=(pick,))
        st.caption("Pick any role to see its plan. Roles are listed in your step 4 ranking order.")
    r = results[titles.index(pick)]
    cons = profile.get("constraints", {})
    c1, c2, c3 = st.columns(3)
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
    plan = build_pathway(r, profile["constraints"], courses)

    with st.container(border=True, key="card_plan"):
        weeks = plan["total_weeks"]
        st.markdown(
            '<div class="v-stats">'
            f'<div class="v-stat"><div class="t">Skill gaps closed</div><div class="n">'
            f'{fx.roll("plan_cov", plan["covered_count"])} of {plan["target_count"]}</div></div>'
            f'<div class="v-stat"><div class="t">Time needed</div><div class="n">'
            f'{fx.roll("plan_weeks", weeks)} week{"" if weeks == 1 else "s"}</div>'
            f'<div class="t">{plan["total_hours"]:g} study hours at {hours} h per week</div></div>'
            f'<div class="v-stat"><div class="t">Cost</div><div class="n">'
            f'RM {fx.roll("plan_cost", plan["total_cost_myr"])}</div></div>'
            '</div>', unsafe_allow_html=True)
        if plan["steps"]:
            if plan["within_timeline"]:
                st.info(f"Fits your {months}-month timeline. It closes {plan['covered_count']} of "
                        f"{plan['target_count']} essential gaps; the rest have no checked course yet.")
            else:
                st.warning(f"Needs about {weeks} weeks, more than your {months}-month timeline. "
                           "Try more hours per week or a longer timeline.")
            st.markdown("**Courses, in order**")
            st.markdown("".join(_course_card(p) for p in plan["steps"]), unsafe_allow_html=True)
        else:
            st.info("None of the courses we have checked cover this role's skill gaps within "
                    "your budget.")
        st.caption("Estimates, not guarantees. You decide what to study and when. "
                   + _sdg_line(r["title"]))

    c1, c2 = st.columns(2)
    if c1.button("Plan details", key="plan_more", icon=":material/info:", width="stretch"):
        _show_dialog("Plan details", _plan_details, r, plan)
    if c2.button("SDG links", key="plan_sdg", icon=":material/public:", width="stretch"):
        _show_dialog("Sustainable Development Goals", _sdg_details, r)
    d1, d2, d3 = st.columns(3)
    d1.download_button("Download my profile (JSON)", icon=":material/download:",
                       data=json.dumps(profile, indent=2, ensure_ascii=True),
                       file_name="shifthappens_profile.json", key="plan_download",
                       width="stretch")
    if d2.button("Show raw JSON", key="plan_raw", icon=":material/data_object:", width="stretch"):
        _show_dialog("Your profile file (raw JSON)", _raw_profile, profile)
    d3.button("Start over", key="plan_start_over", icon=":material/restart_alt:",
              width="stretch", on_click=start_over, disabled=start_over is None)
    st.caption("Your profile file holds no name, age, gender or contact details, and we do "
               "not store it. Upload it on step 1 next time to continue.")