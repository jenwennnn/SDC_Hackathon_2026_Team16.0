"""
signals_views.py
----------------
Step 3 ("Your day"): the donut chart, the three task baskets and supporting views.

  Your day       - donut chart and three baskets of the user's confirmed tasks
                   (AI may take over / AI will assist you / stays mostly human)
  Market board   - all 12 task types ranked by market demand (judges area)
  Changes list   - what moved since the previous data batch (data panel)

Every number, label, colour and basket comes from signals_logic.py, so a task
can never look different in two views.

Used from app.py:
    render_compass(profile, scenario, batch_id)   # main step 3 view
    render_method(profile, scenario, batch_id)    # "How it works (for judges)"
    render_changes(profile, scenario, batch_id)   # "since the previous batch" list
"""

import html
import math

import pandas as pd
import streamlit as st
import fx
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

BORDER = "#EAEAEA"
SOFT_BG = "#FFFFFF"


# ------------------------------ small helpers ------------------------------

def _esc(x):
    return html.escape(str(x))


def _pretty(task_type):
    return TASK_TYPE_NAMES.get(task_type, "Uncategorised")


def _signed(v):
    return f"{v:+.2f}"


def _chip(text, color, risk):
    fg = "#171717" if risk == "medium" else "#FFFFFF"
    return (f'<span style="background:{color};color:{fg};padding:2px 10px;'
            f'border:1px solid {BORDER};border-radius:999px;font-size:0.8rem;'
            f'white-space:nowrap;">{_esc(text)}</span>')


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
                'No trend data for this task yet. Go back to step 2 (Review) and '
                'pick a category for it.</div>')
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


# --------------------------- view 2: Movers board ---------------------------

def _demand_bar(d):
    pct = min(abs(d), 1.0) * 50
    if d >= 0:
        left, color = 50, "#0070F3"
    else:
        left, color = 50 - pct, "#E5484D"
    return (f'<span style="position:relative;display:inline-block;width:120px;'
            f'height:10px;background:#EAEAEA;border-radius:5px;'
            f'vertical-align:middle;">'
            f'<span style="position:absolute;left:{left}%;width:{pct}%;top:0;'
            f'height:10px;background:{color};border-radius:5px;"></span>'
            f'<span style="position:absolute;left:50%;top:-2px;width:1px;'
            f'height:14px;background:#A1A1A1;"></span></span>')


def render_market_board(task_details, data, batch_id, scenarios):
    meta = sl.get_batch(data, batch_id)["meta"]
    prev = sl.previous_batch(data, batch_id)
    prev_id = prev["meta"]["batch_id"] if prev else None
    by_scn = _both_scenarios(sl.build_movers, data, batch_id)
    index = {s: {r["task_type"]: r for r in rows} for s, rows in by_scn.items()}
    order = [r["task_type"] for r in by_scn["steady"]]
    mine = {t.get("task_type") for t in task_details}

    st.markdown("**What the market is doing, task type by task type.** Sorted from "
                "rising demand to falling demand. \u2605 marks task types in your day.")
    st.caption("Bar: blue = demand rising, red = demand falling. "
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


def _resolve_batch(data, batch_id):
    """Use the requested batch if it exists, otherwise the newest one."""
    ids = sl.batch_ids(data)
    return batch_id if batch_id in ids else ids[-1]


def render_changes(profile, scenario, batch_id=None, limit=4):
    """What moved between the chosen batch and the one before it, your task types first."""
    data, err = _load()
    if err:
        st.caption(err)
        return
    batch_id = _resolve_batch(data, batch_id)
    prev = sl.previous_batch(data, batch_id)
    if prev is None:
        st.caption(f"{batch_id} is the oldest data batch, so there is nothing to compare with.")
        return
    prev_id = prev["meta"]["batch_id"]
    rows = sl.build_movers(data, batch_id, scenario)
    mine = {t.get("task_type") for t in _task_details(profile)}
    rows.sort(key=lambda r: (r["task_type"] not in mine, -abs(r["demand_change"] or 0)))
    for r in rows[:limit]:
        d = r["demand_change"] or 0
        word = "up" if d > 0 else ("down" if d < 0 else "unchanged")
        star = " (in your day)" if r["task_type"] in mine else ""
        st.markdown(f"- **{_pretty(r['task_type'])}**{star}: demand {word} "
                    f"{_signed(d)} since {prev_id}, now {_signed(r['demand_index'])}")
    meta = sl.get_batch(data, batch_id)["meta"]
    st.caption(f"Source: {meta['source_name']} | data date {meta['data_date']}"
               + (" | synthetic demo data" if meta.get("is_synthetic") else ""))




# ------------------------- your day: donut and baskets -------------------------

def _polar(cx, cy, deg, r):
    a = math.radians(deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)


def _ai_role_text(rs):
    if rs is None:
        return "unknown"
    if rs >= 0.6:
        return "mostly replaces the work"
    if rs <= 0.4:
        return "mostly assists the person"
    return "partly replaces, partly assists"


def _lean(counts):
    """Text for where the day leans, from basket counts."""
    known = {b: counts[b] for b in sl.BASKETS}
    top = max(known.values()) if known else 0
    if top == 0:
        return None
    leaders = [b for b in sl.BASKETS if known[b] == top]
    names = " and ".join(sl.BASKET_STYLE[b]["label"] for b in leaders)
    return ("Your day leans towards: " if len(leaders) == 1 else "Your day is split between: ") + names


_ANIM = 'dur="0.75s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.2 0.8 0.2 1"'


def _donut_svg(rows, size=320):
    """Donut chart: one slice per basket, sized by how many of the user's tasks are in it.
    Hovering a slice lists its tasks (numbers match the cards below). When the scenario or
    data batch changes, the slices glide from their last position to the new one."""
    cx = cy = size / 2
    r = size / 2 - 34
    width = 44
    circ = 2 * math.pi * r
    numbered = [(i, x) for i, x in enumerate(rows, start=1) if x["basket"] in sl.BASKETS]
    n = len(numbered)
    groups = {b: [(i, x) for i, x in numbered if x["basket"] == b] for b in sl.BASKETS}
    filled = sum(1 for b in sl.BASKETS if groups[b])
    gap = 3 if filled > 1 else 0
    prev = st.session_state.get("_donut_prev") or {}
    now = {}
    parts = [f'<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" role="img" '
             f'aria-label="Donut chart of your tasks by basket">',
             f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#F2F2F2" '
             f'stroke-width="{width}"/>']
    labels = []
    offset = 0.0
    for b in sl.BASKETS:
        members = groups[b]
        style = sl.BASKET_STYLE[b]
        length = circ * len(members) / n if n else 0.0
        dash = max(length - gap, 0.0) if members else 0.0
        now[b] = (dash, offset)
        p_dash, p_off = prev.get(b, (dash, offset))
        if dash > 0 or p_dash > 0:
            tasks = "; ".join(f"{i}. {x['label']}" for i, x in members)
            anim = ""
            if (round(p_dash, 1), round(p_off, 1)) != (round(dash, 1), round(offset, 1)):
                anim = (f'<animate attributeName="stroke-dasharray" '
                        f'from="{p_dash:.2f} {circ - p_dash:.2f}" to="{dash:.2f} {circ - dash:.2f}" {_ANIM}/>'
                        f'<animate attributeName="stroke-dashoffset" from="{-p_off:.2f}" '
                        f'to="{-offset:.2f}" {_ANIM}/>')
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{style["color"]}" '
                f'stroke-width="{width}" stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
                f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})">'
                f'<title>{_esc(style["label"])}: {len(members)} of {n} tasks. {_esc(tasks)}</title>'
                f'{anim}</circle>')
        if members:
            mid = (offset + length / 2) / circ * 360
            lx, ly = _polar(cx, cy, mid, r)
            pct = round(100 * len(members) / n)
            if pct >= 8:
                fade = ('' if b in prev and prev[b] == now[b] else
                        '<animate attributeName="opacity" from="0" to="1" begin="0.55s" dur="0.25s" '
                        'fill="freeze"/>')
                start = ' opacity="0"' if fade else ''
                labels.append(f'<text x="{lx:.1f}" y="{ly + 5:.1f}" text-anchor="middle" '
                              f'font-size="14" font-weight="600" fill="{style["ink"]}"{start} '
                              f'font-family="Geist, sans-serif">{pct}%{fade}</text>')
        offset += length
    parts.extend(labels)
    st.session_state["_donut_prev"] = now
    parts.append(f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="44" '
                 f'font-weight="700" fill="#171717" font-family="Geist, sans-serif" '
                 f'letter-spacing="-1.5">{n}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 28}" text-anchor="middle" font-size="13" '
                 f'fill="#666666" font-family="Geist, sans-serif">daily tasks</text>')
    parts.append('</svg>')
    return "".join(parts)


def _cushions_html(counts):
    total = sum(counts[b] for b in sl.BASKETS) or 1
    out = ['<div class="v-stats">']
    for b in sl.BASKETS:
        st_ = sl.BASKET_STYLE[b]
        pct = round(100 * counts[b] / total)
        out.append(f'<div class="v-stat"><div class="n">{fx.roll("cnt_" + b, counts[b])} '
                   f'<span style="font-size:14px;color:#666666;font-weight:500;">'
                   f'{fx.roll("pct_" + b, pct)}%</span></div>'
                   f'<div class="t"><span class="v-dot" style="background:{st_["color"]};"></span>'
                   f'{_esc(st_["label"])}</div></div>')
    out.append('</div>')
    return "".join(out)


def _card_html(num, f_now, f_other, scenario, prev_id, meta):
    """One task card in a basket. f_now = this scenario, f_other = the other scenario."""
    b = f_now["basket"]
    style = sl.BASKET_STYLE[b]
    demand = f'{f_now["arrow"]} {f_now["demand_label"]}' if f_now["has_data"] else ""
    steady = f_now if scenario == "steady" else f_other
    rapid = f_other if scenario == "steady" else f_now
    lines = [
        f'<b>Why:</b> {_esc(f_now["reason_en"])}',
        f'<b>Category:</b> {_esc(_pretty(f_now["task_type"]))}',
        f'<b>How AI touches it:</b> {_ai_role_text(f_now["replace_share"])}',
        f'<b>AI impact (0 to 1):</b> steady {steady["exposure"]:.2f}, rapid {rapid["exposure"]:.2f}',
        f'<b>Market demand:</b> {_signed(f_now["demand_index"])} '
        f'(-1 = falling fast, +1 = rising fast)',
    ]
    other_name = "rapid" if scenario == "steady" else "steady"
    if f_other["basket"] != b:
        lines.append(f'<b>Under {other_name} AI progress:</b> moves to '
                     f'"{_esc(sl.BASKET_STYLE[f_other["basket"]]["label"])}"')
    else:
        lines.append(f'<b>Under {other_name} AI progress:</b> stays in this basket')
    if prev_id and f_now["demand_change"] is not None:
        lines.append(f'<b>Change since {_esc(prev_id)}:</b> demand {_signed(f_now["demand_change"])}, '
                     f'AI impact {_signed(f_now["exposure_change"])}')
    lines.append(f'<b>Confidence in this estimate:</b> {_esc(f_now["confidence"])}')
    lines.append(f'<b>Source:</b> {_esc(meta["source_name"])}, data date {_esc(meta["data_date"])}'
                 + (', synthetic demo data' if meta.get("is_synthetic") else ''))
    return (f'<details class="v-card"><summary>'
            f'<span class="v-num" style="background:{style["color"]};color:{style["ink"]};">'
            f'{num}</span>'
            f'<span><div class="lbl">{_esc(f_now["label"])}</div>'
            f'<div class="sub">{_esc(demand)}</div>'
            f'<div class="more">Show why</div></span>'
            f'</summary><div class="v-detail">' + "<br>".join(lines) + '</div></details>')


def _compass_rows(profile, scenario, batch_id):
    """(rows for this scenario, rows for the other scenario, data, batch_id, error)."""
    data, err = _load()
    if err:
        return None, None, None, None, err
    batch_id = _resolve_batch(data, batch_id)
    tasks = _task_details(profile)
    other = "rapid" if scenario == "steady" else "steady"
    return (sl.build_my_day(tasks, data, batch_id, scenario),
            sl.build_my_day(tasks, data, batch_id, other), data, batch_id, None)


def render_compass(profile, scenario="steady", batch_id=None):
    rows, other_rows, data, batch_id, err = _compass_rows(profile, scenario, batch_id)
    if err:
        st.error(err)
        return
    if not rows:
        st.info("No confirmed daily tasks yet. Go back to step 2 (Review) and tick the tasks you do.")
        return
    meta = sl.get_batch(data, batch_id)["meta"]
    prev = sl.previous_batch(data, batch_id)
    prev_id = prev["meta"]["batch_id"] if prev else None
    counts = {b: sum(r["basket"] == b for r in rows) for b in sl.BASKETS + ["unknown"]}
    n_known = len(rows) - counts["unknown"]

    with st.container(border=True, key="card_compass"):
        left, right = st.columns([1.15, 1], gap="large")
        with left:
            st.markdown("#### Your day at a glance")
            st.markdown(f"Of your **{n_known}** daily tasks, **{counts['take_over']}** may be taken "
                        f"over by AI, **{counts['assist']}** will be AI-assisted and "
                        f"**{counts['human']}** stay mostly human.")
            st.markdown(_cushions_html(counts), unsafe_allow_html=True)
            lean = _lean(counts)
            if lean:
                st.markdown(f"**{lean}.**")
            st.caption("Each slice is the share of your daily tasks in one basket. Hover a slice "
                       "to see its tasks; the numbers match the cards below. "
                       f"Scenario: {SCENARIO_LABELS[scenario]}. Estimates, not forecasts.")
        with right:
            st.markdown(f'<div class="v-compass">{_donut_svg(rows)}</div>', unsafe_allow_html=True)

    cols = st.columns(3, gap="medium")
    numbered = list(enumerate(rows, start=1))
    for col, b in zip(cols, sl.BASKETS):
        style = sl.BASKET_STYLE[b]
        with col:
            with st.container(border=True, key=f"card_basket_{b}"):
                st.markdown(f'<span class="v-badge"><span class="v-dot" '
                            f'style="background:{style["color"]};"></span>{_esc(style["label"])} '
                            f'&middot; {counts[b]}</span>', unsafe_allow_html=True)
                st.caption(style["meaning"])
                members = [(i, r) for i, r in numbered if r["basket"] == b]
                if not members:
                    st.caption("None of your tasks in this scenario.")
                for i, r in members:
                    st.markdown(_card_html(i, r, other_rows[i - 1], scenario, prev_id, meta),
                                unsafe_allow_html=True)

    missing = [r["label"] for r in rows if r["basket"] == "unknown"]
    if missing:
        st.info(f"{len(missing)} task(s) have no category, so they are not in the chart: "
                + "; ".join(missing) + ". Go back to step 2 (Review) to pick one.")


def render_method(profile, scenario="steady", batch_id=None):
    """Technical view for the judges: the basket rule, the numbers, the market board."""
    rows, _, data, batch_id, err = _compass_rows(profile, scenario, batch_id)
    if err:
        st.caption(err)
        return
    st.markdown(
        f"**How tasks are sorted.** Automation pressure = AI impact x replace share, where "
        f"replace share = (1 - augment index) / 2 (0 = AI only assists, 1 = AI replaces). "
        f"Pressure of {sl.TAKEOVER_PRESSURE_MIN:.2f} or more: *AI may take over*. Otherwise, "
        f"AI impact of {sl.ASSIST_EXPOSURE_MIN:.2f} or more: *AI will assist you*. Otherwise: "
        "*stays mostly human*. The same pressure lowers the role outlook in step 4. "
        "The thresholds are a team assumption.")
    if rows:
        st.dataframe(pd.DataFrame([{
            "Task": r["label"],
            "Category": _pretty(r["task_type"]),
            "AI impact": r["exposure"],
            "Augment index": r["augment_index"],
            "Replace share": r["replace_share"],
            "Pressure": r["pressure"],
            "Basket": sl.BASKET_STYLE[r["basket"]]["label"],
        } for r in rows]), hide_index=True)
    st.markdown("**Market board: all 12 task types**")
    render_market_board(_task_details(profile), data, batch_id, [scenario])