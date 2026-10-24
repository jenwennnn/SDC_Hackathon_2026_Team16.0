"""
build_courses.py
Turns courses_input.csv (filled in by a human) into data/courses.json.
Every course must be opened and checked by a person. Nothing is invented here.

Input:  courses_input.csv   (columns: title, provider, url, cost_type, cost_myr, duration_hours,
                             language, skill_names, date_checked, verified_by)
        data/future_roles.json  (used to turn skill names into ESCO ids)
Output: data/courses.json
Run:    python build_courses.py

Column rules:
  cost_type      free | low_cost | hrd_corp_claimable
  cost_myr       number, leave empty for free courses
  duration_hours number copied from the course page (total hours)
  language       en | ms | zh
  skill_names    one or more skill names separated by ';', copied from skill_shortlist.csv
  date_checked   YYYY-MM-DD, the day you opened the page
  verified_by    your initials
"""
import csv
import json
import sys

INPUT = "courses_input.csv"
OUTPUT = "data/courses.json"
COST_TYPES = {"free", "low_cost", "hrd_corp_claimable"}
LANGS = {"en", "ms", "zh"}


def main():
    with open("data/future_roles.json", encoding="utf-8") as f:
        roles = json.load(f)["roles"]
    name_to_id = {}
    for r in roles:
        for s in r["skills"]:
            name_to_id[s["name"].strip().lower()] = s["esco_id"]

    with open(INPUT, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("courses_input.csv has no rows yet. Add at least one verified course.")

    courses, errors = [], []
    for n, row in enumerate(rows, start=2):   # row 1 is the header
        def bad(msg):
            errors.append(f"Row {n} ({row.get('title', '?')}): {msg}")

        if not row["url"].startswith("http"):
            bad("url must start with http")
        if row["cost_type"] not in COST_TYPES:
            bad(f"cost_type must be one of {sorted(COST_TYPES)}")
        if row["language"] not in LANGS:
            bad(f"language must be one of {sorted(LANGS)}")
        if not row["verified_by"].strip() or not row["date_checked"].strip():
            bad("verified_by and date_checked are required")
        try:
            hours = float(row["duration_hours"])
            if hours <= 0:
                raise ValueError
        except ValueError:
            bad("duration_hours must be a number above 0")
            hours = None
        cost = None
        if row["cost_myr"].strip():
            try:
                cost = float(row["cost_myr"])
            except ValueError:
                bad("cost_myr must be a number or empty")
        if row["cost_type"] == "free" and cost not in (None, 0.0):
            bad("a free course cannot have a cost")

        ids = []
        for name in [x.strip() for x in row["skill_names"].split(";") if x.strip()]:
            eid = name_to_id.get(name.lower())
            if eid is None:
                bad(f"skill '{name}' not found in future_roles.json (copy it from skill_shortlist.csv)")
            else:
                ids.append(eid)
        if not ids:
            bad("at least one skill is required")

        if not errors or not errors[-1].startswith(f"Row {n} "):
            courses.append({
                "course_id": f"crs_{len(courses) + 1:03d}",
                "title": row["title"].strip(),
                "provider": row["provider"].strip(),
                "url": row["url"].strip(),
                "cost_type": row["cost_type"],
                "cost_myr": cost,
                "duration_hours": hours,
                "language": row["language"],
                "skill_ids": ids,
                "source": {"url": row["url"].strip(), "date_checked": row["date_checked"].strip(),
                           "verified_by": row["verified_by"].strip()},
            })

    if errors:
        print("Please fix these problems in courses_input.csv:")
        for e in errors:
            print(" -", e)
        sys.exit(1)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"status": "human_verified", "courses": courses}, f, ensure_ascii=True, indent=1)
    print(f"Done. Wrote {OUTPUT} with {len(courses)} courses.")


if __name__ == "__main__":
    main()
