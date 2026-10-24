"""
signals_logic.py
----------------
The ONE place where signal numbers are turned into colours, labels and arrows.
Every view (task compass, market board) must call these
functions, so the same task can never look different in two views.

No Streamlit code in here on purpose: it can be tested on its own.
"""

import json

SIGNALS_PATH = "data/signals.json"

# ---- The only place thresholds live -------------------------------------
RISK_LOW_BELOW = 0.35      # exposure < 0.35  -> low
RISK_HIGH_ABOVE = 0.65     # exposure > 0.65  -> high (else medium)
DEMAND_UP_ABOVE = 0.15     # demand_index > +0.15 -> rising
DEMAND_DOWN_BELOW = -0.15  # demand_index < -0.15 -> falling
# --------------------------------------------------------------------------

# ---- Task compass baskets (team assumption, shown in the app) ------------
# automation pressure = exposure x replace share, replace share = (1 - augment) / 2
# (the same pieces trend_bridge.py uses for the role outlook)
TAKEOVER_PRESSURE_MIN = 0.30   # pressure >= 0.30            -> AI may take over
ASSIST_EXPOSURE_MIN = 0.30     # else exposure >= 0.30       -> AI will assist you
#                                else                         -> stays mostly human
# --------------------------------------------------------------------------

# Status colours (Vercel Geist style). Everything else in the app is black and white.
RISK_STYLE = {
    "low":     {"label": "Low impact",    "color": "#398E4A"},
    "medium":  {"label": "Medium impact", "color": "#F5A623"},
    "high":    {"label": "High impact",   "color": "#E5484D"},
    "unknown": {"label": "No data",       "color": "#8F8F8F"},
}

BASKETS = ["take_over", "assist", "human"]
BASKET_STYLE = {
    "take_over": {"label": "AI may take over", "color": "#F5A623", "ink": "#171717",
                  "tint": "#FFF4E0", "meaning": "AI can already do much of this work."},
    "assist":    {"label": "AI will assist you", "color": "#0070F3", "ink": "#FFFFFF",
                  "tint": "#EBF4FF", "meaning": "AI speeds this up; you still check and decide."},
    "human":     {"label": "Stays mostly human", "color": "#398E4A", "ink": "#FFFFFF",
                  "tint": "#EDF7EF", "meaning": "Little AI exposure today. Strengths to build on."},
    "unknown":   {"label": "No data", "color": "#8F8F8F", "ink": "#FFFFFF",
                  "tint": "#FAFAFA", "meaning": "This task has no category yet."},
}

DEMAND_STYLE = {
    "up":   {"arrow": "\u25b2", "label": "Demand rising"},
    "down": {"arrow": "\u25bc", "label": "Demand falling"},
    "flat": {"arrow": "\u25ac", "label": "Demand steady"},
}

SCENARIO_NAMES = {
    "steady": "Steady AI progress",
    "rapid": "Rapid AI progress",
}

REQUIRED_SIGNAL_FIELDS = [
    "task_type", "demand_index", "exposure_steady", "exposure_rapid",
    "augment_index", "confidence", "reason_en",
]
REQUIRED_META_FIELDS = ["batch_id", "data_date", "source_name", "is_synthetic"]
VALID_CONFIDENCE = {"low", "medium", "high"}

TASK_TYPES = [
    "data_entry", "document_processing", "customer_communication",
    "internal_communication", "scheduling_coordination", "reporting_writing",
    "calculation_reconciliation", "data_analysis", "content_creation",
    "physical_or_manual", "decision_judgement", "relationship_building",
]


# ---------------------------- loading & checking ----------------------------

def load_signals(path=SIGNALS_PATH):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    problems = validate_signals(data)
    if problems:
        raise ValueError("signals.json has problems:\n- " + "\n- ".join(problems))
    return data


def validate_signals(data):
    """Return a list of problems (empty list = file is OK)."""
    problems = []
    batches = data.get("batches")
    if not batches:
        return ["No batches found."]
    for b in batches:
        meta = b.get("meta", {})
        bid = meta.get("batch_id", "?")
        for field in REQUIRED_META_FIELDS:
            if field not in meta:
                problems.append(f"Batch {bid}: meta missing '{field}'.")
        if not isinstance(meta.get("is_synthetic"), bool):
            problems.append(f"Batch {bid}: is_synthetic must be true or false.")
        seen = set()
        for s in b.get("signals", []):
            tt = s.get("task_type")
            for field in REQUIRED_SIGNAL_FIELDS:
                if field not in s:
                    problems.append(f"Batch {bid}/{tt}: missing '{field}'.")
            if tt not in TASK_TYPES:
                problems.append(f"Batch {bid}: unknown task_type '{tt}'.")
            if tt in seen:
                problems.append(f"Batch {bid}: duplicate task_type '{tt}'.")
            seen.add(tt)
            for field, lo, hi in [("demand_index", -1, 1), ("augment_index", -1, 1),
                                  ("exposure_steady", 0, 1), ("exposure_rapid", 0, 1)]:
                v = s.get(field)
                if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                    problems.append(f"Batch {bid}/{tt}: '{field}' must be a number in [{lo}, {hi}].")
            if s.get("confidence") not in VALID_CONFIDENCE:
                problems.append(f"Batch {bid}/{tt}: confidence must be low/medium/high.")
        missing = set(TASK_TYPES) - seen
        if missing:
            problems.append(f"Batch {bid}: missing task types {sorted(missing)}.")
    return problems


# ------------------------------ batch helpers ------------------------------

def batch_ids(data):
    return [b["meta"]["batch_id"] for b in data["batches"]]


def get_batch(data, batch_id):
    for b in data["batches"]:
        if b["meta"]["batch_id"] == batch_id:
            return b
    raise KeyError(f"No batch called {batch_id}")


def previous_batch(data, batch_id):
    """The batch just before batch_id, or None if it is the oldest."""
    ids = batch_ids(data)
    i = ids.index(batch_id)
    return data["batches"][i - 1] if i > 0 else None


def signals_by_type(batch):
    return {s["task_type"]: s for s in batch["signals"]}


# ------------------------------ the calculators ------------------------------

def normalize_scenario(profile_value):
    """Profile uses 'moderate'/'fast'/'both'. Views use 'steady'/'rapid'.
    Returns a list of scenarios to show."""
    if profile_value == "moderate":
        return ["steady"]
    if profile_value == "fast":
        return ["rapid"]
    return ["steady", "rapid"]


def risk_level(exposure):
    if exposure is None:
        return "unknown"
    if exposure < RISK_LOW_BELOW:
        return "low"
    if exposure > RISK_HIGH_ABOVE:
        return "high"
    return "medium"


def replace_share(augment_index):
    """0 = AI only assists with this kind of task, 1 = AI replaces it."""
    return (1 - augment_index) / 2


def task_basket(exposure, augment_index):
    """Which compass basket a task falls in. Returns (basket, pressure)."""
    if exposure is None or augment_index is None:
        return "unknown", None
    pressure = round(exposure * replace_share(augment_index), 3)
    if pressure >= TAKEOVER_PRESSURE_MIN:
        return "take_over", pressure
    if exposure >= ASSIST_EXPOSURE_MIN:
        return "assist", pressure
    return "human", pressure


def demand_direction(demand_index):
    if demand_index > DEMAND_UP_ABOVE:
        return "up"
    if demand_index < DEMAND_DOWN_BELOW:
        return "down"
    return "flat"


def compute_view_fields(signal, scenario="steady", prev_signal=None):
    """Turn one raw signal into everything a view needs to draw it.

    signal      : one row from signals.json (or None if the task has no type)
    scenario    : 'steady' or 'rapid'
    prev_signal : same task_type from the previous batch (optional)
    """
    if signal is None:
        style = RISK_STYLE["unknown"]
        return {
            "task_type": None, "has_data": False,
            "risk": "unknown", "risk_label": style["label"], "color": style["color"],
            "exposure": None, "demand_index": None,
            "demand_dir": "flat", "arrow": "", "demand_label": "",
            "confidence": None, "reason_en": "No trend data for this task.",
            "demand_change": None, "exposure_change": None,
            "augment_index": None, "replace_share": None,
            "pressure": None, "basket": "unknown",
        }

    exposure = signal["exposure_steady"] if scenario == "steady" else signal["exposure_rapid"]
    risk = risk_level(exposure)
    direction = demand_direction(signal["demand_index"])

    demand_change = exposure_change = None
    if prev_signal is not None:
        demand_change = round(signal["demand_index"] - prev_signal["demand_index"], 2)
        prev_exposure = (prev_signal["exposure_steady"] if scenario == "steady"
                         else prev_signal["exposure_rapid"])
        exposure_change = round(exposure - prev_exposure, 2)

    basket, pressure = task_basket(exposure, signal["augment_index"])
    return {
        "task_type": signal["task_type"], "has_data": True,
        "risk": risk,
        "risk_label": RISK_STYLE[risk]["label"],
        "color": RISK_STYLE[risk]["color"],
        "exposure": exposure,
        "demand_index": signal["demand_index"],
        "demand_dir": direction,
        "arrow": DEMAND_STYLE[direction]["arrow"],
        "demand_label": DEMAND_STYLE[direction]["label"],
        "confidence": signal["confidence"],
        "reason_en": signal["reason_en"],
        "demand_change": demand_change,
        "exposure_change": exposure_change,
        "augment_index": signal["augment_index"],
        "replace_share": round(replace_share(signal["augment_index"]), 3),
        "pressure": pressure,
        "basket": basket,
    }


def build_my_day(task_details, data, batch_id, scenario="steady"):
    """View 1 data: one row per task the user confirmed.
    task_details = profile['current_role']['task_details']."""
    batch = get_batch(data, batch_id)
    prev = previous_batch(data, batch_id)
    now = signals_by_type(batch)
    before = signals_by_type(prev) if prev else {}
    rows = []
    for t in task_details:
        tt = t.get("task_type")
        fields = compute_view_fields(now.get(tt), scenario, before.get(tt))
        fields["label"] = t["label"]
        rows.append(fields)
    return rows


def build_movers(data, batch_id, scenario="steady"):
    """View 2 data: all 12 task types, sorted by demand (biggest riser first)."""
    batch = get_batch(data, batch_id)
    prev = previous_batch(data, batch_id)
    before = signals_by_type(prev) if prev else {}
    rows = [compute_view_fields(s, scenario, before.get(s["task_type"]))
            for s in batch["signals"]]
    rows.sort(key=lambda r: r["demand_index"], reverse=True)
    return rows


def risk_share(rows):
    """Share of the user's tasks in each risk level (for the 'My Day' bar)."""
    n = len(rows)
    counts = {"low": 0, "medium": 0, "high": 0, "unknown": 0}
    for r in rows:
        counts[r["risk"]] += 1
    return {k: (v / n if n else 0.0) for k, v in counts.items()}