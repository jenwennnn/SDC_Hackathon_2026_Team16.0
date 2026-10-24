"""
build_future_roles.py
---------------------
Builds data/future_roles.json (target roles and the skills of each role)
automatically from the ESCO CSV files.
Nothing is typed by hand or invented: role titles, skill names, skill IDs and
role descriptions all come from the ESCO CSV files.

Inputs (all in the data/ folder):
  - data/occupations_en.csv
  - data/occupationSkillRelations_en.csv
  - data/esco_skills_seed_expanded.json  (or esco_skills_seed.json)
  - data/occupation_templates.json
Output:
  - data/future_roles.json

Run:  python build_future_roles.py
"""
import csv
import json
import os
import sys
from datetime import date

DATA_DIR = "data"

# ============ The only thing you normally change: target role list ============
# Must match the ESCO preferredLabel exactly (case does not matter).
TARGET_ROLES = [
    "data analyst",
    "data scientist",
    "data quality specialist",
    "data protection officer",
    "market research analyst",
    "digital marketing manager",
    "client relations manager",
    "customer experience manager",
    "financial analyst",
    "financial controller",
]
# ==============================================================================

# Team assumption (written into the JSON; explain it when presenting):
# ESCO has no proficiency levels, so essential skills require level 3 and
# optional skills require level 2.
LEVEL_BY_RELATION = {"essential": 3, "optional": 2}
WEIGHT_BY_RELATION = {"essential": 1.0, "optional": 0.5}


def find_file(*names):
    for n in names:
        p = os.path.join(DATA_DIR, n)
        if os.path.exists(p):
            return p
    sys.exit(f"File not found: {names}. Make sure it is in the {DATA_DIR}/ folder.")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    occ_rows = read_csv(find_file("occupations_en.csv"))
    rel_rows = read_csv(find_file("occupationSkillRelations_en.csv"))
    seed = read_json(find_file("esco_skills_seed_expanded.json", "esco_skills_seed.json"))
    templates = read_json(find_file("occupation_templates.json"))["templates"]

    seed_ids = {s["esco_id"] for s in seed["skills"]}
    tpl_skill_ids = {t["template_id"]: {s["esco_id"] for s in t["skills"]}
                     for t in templates}

    # Find each role by name (must find exactly 1)
    by_label = {}
    for row in occ_rows:
        by_label.setdefault(row["preferredLabel"].strip().lower(), []).append(row)

    roles = []
    print(f"{'Role':34s} {'Skills':>6s} {'Ess.':>5s} {'In seed':>8s}  Related templates")
    for title in TARGET_ROLES:
        hits = by_label.get(title.strip().lower(), [])
        if len(hits) != 1:
            sys.exit(f"Role '{title}' found {len(hits)} times in ESCO (expected 1). "
                     "Check the spelling, or remove it from the list.")
        occ = hits[0]
        uri = occ["conceptUri"]

        skills, seen = [], set()
        for r in rel_rows:
            if r["occupationUri"] != uri or r["skillUri"] in seen:
                continue
            seen.add(r["skillUri"])
            rel = r["relationType"]  # essential / optional
            skills.append({
                "esco_id": r["skillUri"],
                "name": r["skillLabel"],
                "skill_type": r["skillType"],
                "relation": rel,
                "weight": WEIGHT_BY_RELATION[rel],
                "required_level": LEVEL_BY_RELATION[rel],
                "level_source": "team_assumption",
                "in_seed": r["skillUri"] in seed_ids,
            })
        # Essential skills first
        skills.sort(key=lambda s: (s["relation"] != "essential", s["name"]))

        role_skill_ids = {s["esco_id"] for s in skills}
        related = [tid for tid, ids in tpl_skill_ids.items()
                   if len(ids & role_skill_ids) >= 2]
        overlap = sum(1 for s in skills if s["in_seed"])
        n_ess = sum(1 for s in skills if s["relation"] == "essential")
        print(f"{occ['preferredLabel']:34s} {len(skills):6d} {n_ess:5d} {overlap:8d}  {related}")

        roles.append({
            "role_id": uri,
            "title": occ["preferredLabel"],
            "isco_group": occ["iscoGroup"],
            "description": occ["description"].strip(),
            "from_templates": related,
            "sdg_tags": [],
            "sdg_status": "todo_not_mapped_yet",
            "skills": skills,
            "source": {
                "name": "ESCO",
                "files": ["occupations_en.csv", "occupationSkillRelations_en.csv"],
                "url": uri,
            },
        })

    out = {
        "source": "ESCO (occupations_en.csv + occupationSkillRelations_en.csv)",
        "esco_version_note": (f"Seed file says version {seed.get('version')}. "
                              "Check that the CSV files are the same ESCO version."),
        "generated": date.today().isoformat(),
        "status": "draft_needs_human_review",
        "level_note": ("ESCO does not provide proficiency levels. required_level is a "
                       "team assumption: essential = 3, optional = 2."),
        "roles": roles,
    }
    out_path = os.path.join(DATA_DIR, "future_roles.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=True, indent=1)
    print(f"\nDone. Wrote {out_path} with {len(roles)} roles.")


if __name__ == "__main__":
    main()