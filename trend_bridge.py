"""
trend_bridge.py
---------------
Connects the trend signal layer (data/signals.json, per TASK TYPE) to the
matcher (which needs trend scores per ESCO SKILL, keyed by esco_id).

  signals.json  --(task type demand_index)-->  skill_task_map.json  -->  {esco_id: score}

No Streamlit code here, so it can be tested on its own:
    python trend_bridge.py

Scenarios: the same trend scores are used in both scenarios. What changes is
how strongly trend affects the matcher weights (SCENARIO_STRENGTH). These
strengths are a TEAM ASSUMPTION used to show uncertainty, not a forecast.
"""

import json

import signals_logic as sl

SKILL_MAP_PATH = "data/skill_task_map.json"

# How strongly trend changes skill weights in the matcher, per scenario.
# Team assumption: rapid AI progress makes market shifts count twice as much.
SCENARIO_STRENGTH = {
    "steady": 0.25,
    "rapid": 0.5,
}
SCENARIO_LABELS = {
    "steady": "Steady AI progress",
    "rapid": "Rapid AI progress",
}


def load_skill_map(path=SKILL_MAP_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def latest_batch_id(signals):
    return sl.batch_ids(signals)[-1]


def build_trend(signals, skill_map, batch_id=None):
    """Return {esco_id: demand_index} for every mapped skill.
    Skills with no task type are left out (the matcher treats them as 0)."""
    batch_id = batch_id or latest_batch_id(signals)
    by_type = sl.signals_by_type(sl.get_batch(signals, batch_id))
    trend = {}
    for esco_id, info in skill_map["skills"].items():
        tt = info.get("task_type")
        if tt and tt in by_type:
            trend[esco_id] = by_type[tt]["demand_index"]
    return trend


def trend_info(signals, batch_id=None):
    """Source, date and synthetic flag of the batch, for display."""
    batch_id = batch_id or latest_batch_id(signals)
    meta = sl.get_batch(signals, batch_id)["meta"]
    return {
        "batch_id": batch_id,
        "source_name": meta["source_name"],
        "data_date": meta["data_date"],
        "is_synthetic": bool(meta.get("is_synthetic")),
    }


def trend_label(value):
    """Word label for one skill trend value (same thresholds as the radar)."""
    if value is None:
        return "no data"
    return {"up": "rising", "down": "falling", "flat": "steady"}[sl.demand_direction(value)]


# ---------------- self test: python trend_bridge.py ----------------
if __name__ == "__main__":
    sig = sl.load_signals()
    smap = load_skill_map()
    t = build_trend(sig, smap)
    print(trend_info(sig))
    print(f"{len(t)} skills have a trend score.")
    for eid, v in list(t.items())[:5]:
        print(f"  {v:+.2f}  {smap['skills'][eid]['name']}")
