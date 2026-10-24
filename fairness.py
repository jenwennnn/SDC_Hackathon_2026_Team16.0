"""
fairness.py - automatic fairness check (deterministic, no LLM)

What it checks
  1. Protected attributes cannot change the results. We copy the profile, add or
     change name, age, gender, race, religion, nationality, marital status,
     disability, contact details, years of experience, job title and industry,
     and confirm that the role ranking, scores and skill gaps stay exactly the same.
  2. The profile does not store protected attributes.

What it does NOT check (stated honestly in the app)
  - Bias inside the ESCO data or our team mappings.
  - Bias in how the language model reads a CV. The user reviews and edits every
    extracted skill before matching, which limits this risk.

Run on its own:  python fairness.py
"""
import copy
import json

from matcher import load_roles, match_roles, rank_by_future_fit

PROTECTED_FIELDS = ["name", "age", "gender", "race", "ethnicity", "religion", "nationality",
                    "marital_status", "disability", "email", "phone"]

VARIANTS = [
    ("name", {"name": "Test Person A"}),
    ("age 22", {"age": 22}),
    ("age 55", {"age": 55}),
    ("gender female", {"gender": "female"}),
    ("gender male", {"gender": "male"}),
    ("race / ethnicity", {"race": "group B", "ethnicity": "group B"}),
    ("religion", {"religion": "group C"}),
    ("nationality", {"nationality": "non-Malaysian"}),
    ("marital status", {"marital_status": "married"}),
    ("disability", {"disability": "yes"}),
    ("contact details", {"email": "test@example.com", "phone": "0123456789"}),
]
ROLE_VARIANTS = [
    ("years of experience 0-1", {"years_experience": "0-1"}),
    ("years of experience 10+", {"years_experience": "10+"}),
    ("different job title and industry", {"title": "Other title", "industry": "Other industry"}),
]


def _fingerprint(profile, roles, trend, outlook_weight):
    results = rank_by_future_fit(match_roles(profile, roles, trend=trend), outlook_weight)
    return [(r["title"], r["match_score"], r["future_fit"],
             tuple(g["esco_id"] for g in r["gaps"])) for r in results]


def check_fairness(profile, roles, trend=None, outlook_weight=0.5):
    """Return {"passed": bool, "tests": [(name, passed)], "stored_protected": [fields]}."""
    base = _fingerprint(profile, roles, trend, outlook_weight)
    tests = []
    for name, extra in VARIANTS:
        variant = copy.deepcopy(profile)
        variant.update(extra)
        tests.append((name, _fingerprint(variant, roles, trend, outlook_weight) == base))
    for name, extra in ROLE_VARIANTS:
        variant = copy.deepcopy(profile)
        variant.setdefault("current_role", {}).update(extra)
        tests.append((name, _fingerprint(variant, roles, trend, outlook_weight) == base))
    stored = [f for f in PROTECTED_FIELDS
              if f in profile or f in (profile.get("current_role") or {})]
    return {"passed": all(ok for _, ok in tests) and not stored,
            "tests": tests, "stored_protected": stored}


# ---------------- self test: python fairness.py ----------------
if __name__ == "__main__":
    roles = load_roles()
    with open("data/occupation_templates.json", encoding="utf-8") as f:
        templates = json.load(f)["templates"]
    for tpl in templates:
        prof = {"skills": [{"esco_id": s["esco_id"], "level": s["default_level"]}
                           for s in tpl["skills"]],
                "current_role": {"title": tpl["display_name"]["en"]}}
        result = check_fairness(prof, roles)
        print(f"{tpl['display_name']['en']:36s} passed={result['passed']} "
              f"({sum(ok for _, ok in result['tests'])}/{len(result['tests'])} tests)")