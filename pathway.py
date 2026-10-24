"""
pathway.py - ordered reskilling plan (deterministic, no LLM)

Input:
  role_result : one item from matcher.match_roles(...) (has "gaps" with priority and level_gap)
  constraints : dict with hours_per_week, budget (free | low_cost | hrd_corp_claimable),
                timeline_months, language (en | ms | zh)
  courses     : list from data/courses.json (human-verified courses only)
Output (dict):
  steps        : ordered courses, each with the gap skills it covers, hours, cost, start/end week
  uncovered    : essential gap skills that no course in our list covers (shown honestly)
  total_hours, total_weeks, total_cost_myr, within_timeline, assumptions

Method (simple and explainable):
  1. Target = essential skills where you are below the required level.
  2. Keep only courses allowed by your budget.
  3. Repeatedly pick the course with the most gap value per hour
     (value = sum of the priority of the still-uncovered target skills it teaches).
  4. Weeks = total hours / hours per week.
"""
import json
import math
import os

WEEKS_PER_MONTH = 4.33
ALLOWED_COST = {
    "free": {"free"},
    "low_cost": {"free", "low_cost"},
    "hrd_corp_claimable": {"free", "low_cost", "hrd_corp_claimable"},
}
ASSUMPTIONS = [
    "Finishing a course is assumed to bring a skill up to the level the role needs. "
    "Real mastery also needs practice on the job.",
    "Course hours are the total time shown on each course page. Your pace may differ.",
    "The plan only uses courses our team has checked by hand, so some skills may have no course yet.",
    "Required levels are a team assumption (essential = 3, optional = 2).",
]


def load_courses(path="data/courses.json"):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("courses", [])


def build_pathway(role_result, constraints, courses):
    hours_pw = max(1, int(constraints.get("hours_per_week", 5)))
    budget = constraints.get("budget", "free")
    language = constraints.get("language", "en")
    months = constraints.get("timeline_months", 6)

    # 1. target skills: essential and still below the required level
    targets = {g["esco_id"]: g for g in role_result["gaps"]
               if g["relation"] == "essential" and g["level_gap"] > 0}

    # 2. budget filter
    allowed = ALLOWED_COST.get(budget, {"free"})
    pool = [c for c in courses if c["cost_type"] in allowed]

    # 3. greedy pick by value per hour
    remaining = dict(targets)
    steps, used = [], set()
    while remaining:
        best, best_key = None, None
        for c in pool:
            if c["course_id"] in used:
                continue
            covered = [sid for sid in c["skill_ids"] if sid in remaining]
            if not covered:
                continue
            value = sum(remaining[sid]["priority"] for sid in covered)
            density = value / c["duration_hours"]
            # higher density first, then cheaper, then preferred language
            key = (round(density, 6), -(c["cost_myr"] or 0), c["language"] == language)
            if best_key is None or key > best_key:
                best, best_key = (c, covered), key
        if best is None:
            break
        course, covered = best
        used.add(course["course_id"])
        steps.append((course, covered))
        for sid in covered:
            remaining.pop(sid, None)

    # 4. timeline
    plan, cum_hours, total_cost = [], 0.0, 0.0
    for i, (c, covered) in enumerate(steps, start=1):
        start_week = math.floor(cum_hours / hours_pw) + 1
        cum_hours += c["duration_hours"]
        end_week = math.ceil(cum_hours / hours_pw)
        total_cost += c["cost_myr"] or 0
        plan.append({
            "order": i,
            "course_id": c["course_id"],
            "title": c["title"],
            "provider": c["provider"],
            "url": c["url"],
            "cost_type": c["cost_type"],
            "cost_myr": c["cost_myr"],
            "duration_hours": c["duration_hours"],
            "language": c["language"],
            "language_match": c["language"] == language,
            "covers": [targets[sid]["name"] for sid in covered],
            "start_week": start_week,
            "end_week": end_week,
            "source": c["source"],
        })

    total_weeks = math.ceil(cum_hours / hours_pw) if cum_hours else 0
    return {
        "role_title": role_result["title"],
        "steps": plan,
        "uncovered": list(remaining.values()),
        "target_count": len(targets),
        "covered_count": len(targets) - len(remaining),
        "total_hours": cum_hours,
        "total_weeks": total_weeks,
        "total_cost_myr": total_cost,
        "timeline_weeks": round(months * WEEKS_PER_MONTH),
        "within_timeline": total_weeks <= round(months * WEEKS_PER_MONTH),
        "assumptions": ASSUMPTIONS,
    }
