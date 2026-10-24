"""
trend_bridge.py
---------------
Connects the trend signal layer (data/signals.json, per TASK TYPE) to the
matcher (which needs trend scores per ESCO SKILL, keyed by esco_id).

  signals.json  --(task type outlook)-->  skill_task_map.json  -->  {esco_id: score}

No Streamlit code here, so it can be tested on its own:
    python trend_bridge.py

Scenarios: each skill gets an OUTLOOK score per scenario:

    replace_share     = (1 - augment_index) / 2      0 = AI only assists, 1 = AI replaces
    automation_press. = exposure_<scenario> x replace_share
    outlook           = demand_index - automation_pressure   (kept in -1..+1)

exposure_steady and exposure_rapid come from data/signals.json, so the two
scenarios differ because the data says AI touches tasks more under rapid
progress, not because of an extra hand-picked multiplier. The formula is a
TEAM ASSUMPTION used to explore uncertainty, not a forecast.
"""

import json

import signals_logic as sl

SKILL_MAP_PATH = "data/skill_task_map.json"

SCENARIOS = ["steady", "rapid"]
SCENARIO_LABELS = {
    "steady": "Steady AI progress",
    "rapid": "Rapid AI progress",
}


def load_skill_map(path=SKILL_MAP_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def latest_batch_id(signals):
    return sl.batch_ids(signals)[-1]


def clamp(value, low=-1.0, high=1.0):
    return max(low, min(high, value))


def task_outlook(signal, scenario):
    """Outlook of one task type under one scenario (see formula at the top)."""
    exposure = signal["exposure_steady"] if scenario == "steady" else signal["exposure_rapid"]
    replace_share = (1 - signal["augment_index"]) / 2
    return round(clamp(signal["demand_index"] - exposure * replace_share), 2)


def build_trend(signals, skill_map, batch_id=None, scenario="steady"):
    """Return {esco_id: outlook} for every mapped skill under one scenario.
    Skills with no task type are left out (the matcher treats them as 0)."""
    batch_id = batch_id or latest_batch_id(signals)
    by_type = sl.signals_by_type(sl.get_batch(signals, batch_id))
    outlook_by_type = {tt: task_outlook(sig, scenario) for tt, sig in by_type.items()}
    trend = {}
    for esco_id, info in skill_map["skills"].items():
        tt = info.get("task_type")
        if tt in outlook_by_type:
            trend[esco_id] = outlook_by_type[tt]
    return trend


def build_trends(signals, skill_map, batch_id=None):
    """Both scenarios at once: {"steady": {...}, "rapid": {...}}."""
    return {scn: build_trend(signals, skill_map, batch_id, scn) for scn in SCENARIOS}


def outlook_table(signals, batch_id=None):
    """One row per task type with the inputs and the outlook in each scenario."""
    batch_id = batch_id or latest_batch_id(signals)
    rows = []
    for sig in sl.get_batch(signals, batch_id)["signals"]:
        rows.append({
            "task_type": sig["task_type"],
            "demand_index": sig["demand_index"],
            "augment_index": sig["augment_index"],
            "exposure_steady": sig["exposure_steady"],
            "exposure_rapid": sig["exposure_rapid"],
            "outlook_steady": task_outlook(sig, "steady"),
            "outlook_rapid": task_outlook(sig, "rapid"),
        })
    rows.sort(key=lambda r: r["outlook_steady"], reverse=True)
    return rows


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
    print(trend_info(sig))
    print(f"{len(build_trend(sig, smap))} skills have an outlook score.")
    print(f"{'task type':28s} {'steady':>7s} {'rapid':>7s}")
    for r in outlook_table(sig):
        print(f"{r['task_type']:28s} {r['outlook_steady']:+7.2f} {r['outlook_rapid']:+7.2f}")