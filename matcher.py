"""
matcher.py - future role matching (deterministic, no LLM)

Input:
  1. profile: the final_profile built by app.py (uses esco_id and level in profile["skills"])
  2. roles: the roles list from data/future_roles.json
  3. trend (optional): {esco_id: number}, from -1 (declining) to +1 (rising)
Output:
  A list sorted by match_score (high to low). Each item has: match_score (0-100),
  essential_coverage, essential_have / essential_total, matched / partial / gaps,
  explanation, source.

Scoring (fully explainable):
  For each role skill:  coverage = min(your level / required level, 1)   (missing skill = 0)
  match_score = sum(weight x coverage) / sum(weight) x 100
  Weights: essential 1.0, optional 0.5 (from future_roles.json)
  Trend (optional): rising skills get more weight, declining skills less (TREND_STRENGTH)
"""
import json

TREND_STRENGTH = 0.5   # how much trend changes the weight. 0 = ignore trend
MIN_WEIGHT = 0.1       # weight never drops below this


def load_roles(path="data/future_roles.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["roles"]


def user_skill_levels(profile):
    """Return {esco_id: level}. Duplicates keep the highest level; unmapped skills are skipped."""
    levels = {}
    for s in profile.get("skills", []):
        eid = s.get("esco_id")
        if not eid:
            continue
        levels[eid] = max(levels.get(eid, 0), int(s.get("level", 0)))
    return levels


def score_role(role, levels, trend=None):
    total_w = 0.0
    got_w = 0.0
    matched, partial, gaps = [], [], []
    ess_total = ess_have = 0

    for sk in role["skills"]:
        w = sk["weight"]
        if trend and sk["esco_id"] in trend:
            w = max(MIN_WEIGHT, w * (1 + TREND_STRENGTH * trend[sk["esco_id"]]))

        need = sk["required_level"]
        have = levels.get(sk["esco_id"], 0)
        cov = min(have / need, 1.0) if need else 1.0

        total_w += w
        got_w += w * cov
        if sk["relation"] == "essential":
            ess_total += 1
            ess_have += 1 if cov >= 1.0 else 0

        item = {
            "esco_id": sk["esco_id"],
            "name": sk["name"],
            "relation": sk["relation"],
            "your_level": have,
            "required_level": need,
            "level_gap": max(need - have, 0),
            "priority": round(w * (1 - cov), 3),   # higher = learn this first
        }
        if cov >= 1.0:
            matched.append(item)
        elif have > 0:
            partial.append(item)
            gaps.append(item)
        else:
            gaps.append(item)

    gaps.sort(key=lambda g: g["priority"], reverse=True)
    score = round(100 * got_w / total_w, 1) if total_w else 0.0
    ess_cov = round(100 * ess_have / ess_total, 1) if ess_total else 0.0

    explanation = (
        f"You fully meet {len(matched)} of {len(role['skills'])} skills "
        f"({ess_have} of {ess_total} essential). "
        f"{len(partial)} are partly covered and {len(gaps) - len(partial)} are missing."
    )
    return {
        "role_id": role["role_id"],
        "title": role["title"],
        "match_score": score,
        "essential_coverage": ess_cov,
        "essential_have": ess_have,
        "essential_total": ess_total,
        "matched": matched,
        "partial": partial,
        "gaps": gaps,                       # sorted by priority
        "explanation": explanation,
        "source": role["source"],           # every recommendation carries its source
        "sdg_tags": role.get("sdg_tags", []),
    }


def match_roles(profile, roles, trend=None, top_n=None):
    levels = user_skill_levels(profile)
    results = [score_role(r, levels, trend) for r in roles]
    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results[:top_n] if top_n else results


# ---------------- self test: python matcher.py ----------------
if __name__ == "__main__":
    roles = load_roles()
    with open("data/occupation_templates.json", encoding="utf-8") as f:
        templates = json.load(f)["templates"]

    for tpl in templates:
        fake_profile = {"skills": [{"esco_id": s["esco_id"], "level": s["default_level"]}
                                   for s in tpl["skills"]]}
        print(f"\n=== User: {tpl['display_name']['en']} ===")
        for r in match_roles(fake_profile, roles, top_n=3):
            top_gap = ", ".join(g["name"] for g in r["gaps"][:3])
            print(f"  {r['match_score']:5.1f}  {r['title']:30s} start with: {top_gap}")