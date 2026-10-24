"""
signals_views.py
----------------
Draws the Future Skills Radar: two views of the SAME data.

  View 1 "My Day"       - the user's own confirmed tasks, coloured by AI impact
  View 2 "Movers board" - all 12 task types ranked by market demand

Both views get every number, colour and arrow from signals_logic.py, so the
same task can never look different in the two views.

Used from app.py (step 3, "Your day"):
    render_signals_section(profile, scenario)   # My Day and Movers board
    render_changes(profile, scenario)           # "since the last data update" list
    render_day_summary(profile, scenario)       # compact bar (optional)
The scenario ('steady' or 'rapid') comes from the one shared switch in app.py.
"""

import html
import streamlit as st
import signals_logic as sl

# Display names only (no numbers live here).
TASK_TYPE_NAMES = {
    "data_entry": "Data entry",
    "document_processing": "Document handling",
    "customer_communication": "Customer communication",
    "internal_communication": "Internal communication",
    "scheduling_coordination": "Scheduling & coordination",
    "reporting_writing": "Reports & writing",
    "calculation_reconciliation": "Calculation & checking",
    "data_analysis": "Data analysis",
    "content_creation": "Content creation",
    "physical_or_manual": "Hands-on / manual work",
    "decision_judgement": "Judgement & decisions",
    "relationship_building": "Relationship building",
}

SCENARIO_LABELS = {
    "steady": "Steady AI progress",
    "rapid": "Rapid AI progress",
    "both": "Show both",
}
SCENARIO_SHORT = {"steady": "Steady", "rapid": "Rapid"}
VIEW_CHOICES = ["My Day", "Movers board"]

BORDER = "rgba(128,128,128,.35)"
SOFT_BG = "rgba(128,128,128,.07)"


# ------------------------------ small helpers ------------------------------

def _esc(x):
    return html.escape(str(x))


def _pretty(task_type):
    return TASK_TYPE_NAMES.get(task_type, "Uncategorised")


def _signed(v):
    return f"{v:+.2f}"


def _chip(text, color, risk):
    fg = "#1b1b1b" if risk in ("medium", "unknown") else "#ffffff"
    return (f'<span style="background:{color};color:{fg};padding:2px 9px;'
            f'border-radius:10px;font-size:0.8rem;white-space:nowrap;">{_esc(text)}</span>')


def _chips(fields_by_scn, scenarios):
    parts = []
    for s in scenarios:
        f = fields_by_scn[s]
        text = f["risk_label"] if len(scenarios) == 1 else f'{SCENARIO_SHORT[s]}: {f["risk_label"]}'
        parts.append(_chip(text, f["color"], f["risk"]))
    return " ".join(parts)


def _detail_html(fields_by_scn, prev_id, meta):
    """The 'why' panel. Same content in both views."""
    f = fields_by_scn["steady"]
    if not f["has_data"]:
        return ('<div style="margin-top:8px;font-size:0.9rem;">'
                'No trend data for this task yet. Tasks from a CV upload are '
                'sorted into categories in a later step.</div>')
    r = fields_by_scn["rapid"]
    lines = [
        f'<b>Why:</b> {_esc(f["reason_en"])}',
        f'<b>Category:</b> {_esc(_pretty(f["task_type"]))}',
        f'<b>Demand index:</b> {_signed(f["demand_index"])} '
        f'(-1 = falling fast, +1 = rising fast)',
        f'<b>AI impact (0 to 1):</b> Steady {f["exposure"]:.2f} ({_esc(f["risk_label"])}) '
        f'&middot; Rapid {r["exposure"]:.2f} ({_esc(r["risk_label"])})',
    ]
    if prev_id and f["demand_change"] is not None:
        lines.append(
            f'<b>Change since {_esc(prev_id)}:</b> demand {_signed(f["demand_change"])}, '
            f'AI impact steady {_signed(f["exposure_change"])} / rapid {_signed(r["exposure_change"])}')
    else:
        lines.append('<b>Change:</b> no earlier batch to compare with.')
    lines.append(f'<b>Confidence in this estimate:</b> {_esc(f["confidence"])}')
    lines.append(f'<b>Source:</b> {_esc(meta["source_name"])} &middot; data date '
                 f'{_esc(meta["data_date"])}'
                 + (' &middot; synthetic demo data' if meta.get("is_synthetic") else ''))
    return ('<div style="margin-top:8px;font-size:0.9rem;line-height:1.6;">'
            + "<br>".join(lines) + '</div>')


def _both_scenarios(builder, *args):
    """Always compute both scenarios so the detail panel can show both."""
    return {s: builder(*args, s) for s in ("steady", "rapid")}


# ----------------------------- view 1: My Day -----------------------------

def _day_bar(rows):
    segs = "".join(
        f'<div title="{_esc(r["label"])}: {_esc(r["risk_label"])}" '
        f'style="flex:1;background:{r["color"]};"></div>'
        for r in rows
    )
    return (f'<div style="display:flex;gap:3px;height:30px;border-radius:8px;'
            f'overflow:hidden;margin:4px 0 6px 0;">{segs}</div>')


def _summary_text(rows):
    n = len(rows)
    counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for r in rows:
        counts[r["risk"]] += 1
    text = (f"{counts['high']} of {n} tasks high impact, "
            f"{counts['medium']} medium, {counts['low']} low")
    if counts["unknown"]:
        text += f", {counts['unknown']} without data"
    return text


def _render_my_day(task_details, data, batch_id, scenarios):
    if not task_details:
        st.info("No confirmed daily tasks yet. Go back to step 2 (Review) and tick "
                "the tasks you do.")
        return

    meta = sl.get_batch(data, batch_id)["meta"]
    prev = sl.previous_batch(data, batch_id)
    prev_id = prev["meta"]["batch_id"] if prev else None
    by_scn = _both_scenarios(sl.build_my_day, task_details, data, batch_id)

    st.markdown("**Your working day, split by task.** Each block is one of your "
                "tasks; colour shows how much AI can already touch it.")
    for s in scenarios:
        st.markdown(f"Scenario: {SCENARIO_LABELS[s]}")
        st.markdown(_day_bar(by_scn[s]), unsafe_allow_html=True)
        st.caption(_summary_text(by_scn[s]))
    st.caption("Colour key: green = low impact, yellow = medium, red = high, "
               "grey = no data.")

    st.markdown("**Tap a task to see why.**")
    for i in range(len(task_details)):
        f_by = {s: by_scn[s][i] for s in ("steady", "rapid")}
        f0 = f_by["steady"]
        label = by_scn["steady"][i]["label"]
        demand = f"{f0['arrow']} {f0['demand_label']}" if f0["has_data"] else ""
        row = (
            f'<details style="border:1px solid {BORDER};border-radius:8px;'
            f'padding:8px 12px;margin:6px 0;background:{SOFT_BG};">'
            f'<summary style="cursor:pointer;">'
            f'<span style="display:inline-block;min-width:60%;">&#9656; {_esc(label)}</span> '
            f'{_chips(f_by, scenarios)} '
            f'<span style="margin-left:6px;">{_esc(demand)}</span>'
            f'</summary>'
            f'{_detail_html(f_by, prev_id, meta)}'
            f'</details>'
        )
        st.markdown(row, unsafe_allow_html=True)


# --------------------------- view 2: Movers board ---------------------------

def _demand_bar(d):
    pct = min(abs(d), 1.0) * 50
    if d >= 0:
        left, color = 50, "#3b82f6"
    else:
        left, color = 50 - pct, "#f59e0b"
    return (f'<span style="position:relative;display:inline-block;width:120px;'
            f'height:10px;background:rgba(128,128,128,.25);border-radius:5px;'
            f'vertical-align:middle;">'
            f'<span style="position:absolute;left:{left}%;width:{pct}%;top:0;'
            f'height:10px;background:{color};border-radius:5px;"></span>'
            f'<span style="position:absolute;left:50%;top:-2px;width:1px;'
            f'height:14px;background:rgba(128,128,128,.8);"></span></span>')


def _render_movers(task_details, data, batch_id, scenarios):
    meta = sl.get_batch(data, batch_id)["meta"]
    prev = sl.previous_batch(data, batch_id)
    prev_id = prev["meta"]["batch_id"] if prev else None
    by_scn = _both_scenarios(sl.build_movers, data, batch_id)
    index = {s: {r["task_type"]: r for r in rows} for s, rows in by_scn.items()}
    order = [r["task_type"] for r in by_scn["steady"]]
    mine = {t.get("task_type") for t in task_details}

    st.markdown("**What the market is doing, task type by task type.** Sorted from "
                "rising demand to falling demand. \u2605 marks task types in your day.")
    st.caption("Bar: blue = demand rising, orange = demand falling. "
               "Chip: how much AI can already touch this kind of task.")

    for tt in order:
        f_by = {s: index[s][tt] for s in ("steady", "rapid")}
        f0 = f_by["steady"]
        star = "&#9733; " if tt in mine else ""
        change = ""
        if prev_id and f0["demand_change"] is not None:
            arrow = "&#9650;" if f0["demand_change"] > 0 else ("&#9660;" if f0["demand_change"] < 0 else "&#9644;")
            change = (f'<span style="font-size:0.8rem;opacity:.8;">{arrow} '
                      f'{_signed(f0["demand_change"])} since {_esc(prev_id)}</span>')
        row = (
            f'<details style="border:1px solid {BORDER};border-radius:8px;'
            f'padding:8px 12px;margin:6px 0;background:{SOFT_BG};">'
            f'<summary style="cursor:pointer;">'
            f'<span style="display:inline-block;min-width:190px;">'
            f'{star}{_esc(_pretty(tt))}</span> '
            f'{_demand_bar(f0["demand_index"])} '
            f'<span style="display:inline-block;min-width:60px;">'
            f'{f0["arrow"]} {_signed(f0["demand_index"])}</span> '
            f'{_chips(f_by, scenarios)} {change}'
            f'</summary>'
            f'{_detail_html(f_by, prev_id, meta)}'
            f'</details>'
        )
        st.markdown(row, unsafe_allow_html=True)


# ------------------------------- entry point -------------------------------

def _load():
    """Return (data, error_text)."""
    try:
        return sl.load_signals(), None
    except FileNotFoundError:
        return None, "Trend data not found. Run `python generate_signals.py` first."
    except ValueError as e:
        return None, str(e)


def _task_details(profile):
    return profile.get("current_role", {}).get("task_details", [])


def day_counts(profile, scenario):
    """{'high': n, 'medium': n, 'low': n, 'unknown': n, 'total': n} for the latest batch, or None."""
    data, err = _load()
    tasks = _task_details(profile)
    if err or not tasks:
        return None
    rows = sl.build_my_day(tasks, data, sl.batch_ids(data)[-1], scenario)
    counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for r in rows:
        counts[r["risk"]] += 1
    counts["total"] = len(rows)
    return counts


def render_day_summary(profile, scenario):
    """Compact 'your day' bar for the Overview page."""
    data, err = _load()
    if err:
        st.caption(err)
        return
    tasks = _task_details(profile)
    if not tasks:
        st.caption("No confirmed daily tasks yet. Add them in step 2 (Review).")
        return
    rows = sl.build_my_day(tasks, data, sl.batch_ids(data)[-1], scenario)
    st.markdown(_day_bar(rows), unsafe_allow_html=True)
    st.caption(_summary_text(rows) + ". Green = low, yellow = medium, red = high, grey = no data.")


def render_changes(profile, scenario, limit=4):
    """What moved between the two latest batches, your task types first."""
    data, err = _load()
    if err:
        st.caption(err)
        return
    ids = sl.batch_ids(data)
    if len(ids) < 2:
        st.caption("Only one data batch so far. Changes appear after the next update.")
        return
    rows = sl.build_movers(data, ids[-1], scenario)
    mine = {t.get("task_type") for t in _task_details(profile)}
    rows.sort(key=lambda r: (r["task_type"] not in mine, -abs(r["demand_change"] or 0)))
    for r in rows[:limit]:
        d = r["demand_change"] or 0
        word = "up" if d > 0 else ("down" if d < 0 else "unchanged")
        star = " (in your day)" if r["task_type"] in mine else ""
        st.markdown(f"- **{_pretty(r['task_type'])}**{star}: demand {word} "
                    f"{_signed(d)} since {ids[-2]}, now {_signed(r['demand_index'])}")
    meta = sl.get_batch(data, ids[-1])["meta"]
    st.caption(f"Source: {meta['source_name']} | data date {meta['data_date']}"
               + (" | synthetic demo data" if meta.get("is_synthetic") else ""))


def render_signals_section(profile, scenario="steady"):
    data, err = _load()
    if err:
        st.error(err)
        return

    ids = sl.batch_ids(data)
    c1, c2 = st.columns(2)
    with c1:
        batch_id = st.selectbox(
            "Data batch", ids, index=len(ids) - 1, key="sig_batch",
            format_func=lambda b: f"{b} (data date {sl.get_batch(data, b)['meta']['data_date']})")
    with c2:
        view = st.radio("View", VIEW_CHOICES, key="sig_view", horizontal=True)
    scenarios = [scenario]

    task_details = profile.get("current_role", {}).get("task_details", [])
    if view == "My Day":
        _render_my_day(task_details, data, batch_id, scenarios)
    else:
        _render_movers(task_details, data, batch_id, scenarios)