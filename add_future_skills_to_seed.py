"""
add_future_skills_to_seed.py
Adds skills that are essential for several target roles to the seed file.
Rule: if a skill is essential in >= MIN_ROLES target roles and is not in the seed yet, add it.
Skill names and IDs come from ESCO (via future_roles.json). Nothing is invented.

Input:  data/future_roles.json, data/esco_skills_seed_expanded.json
Output: data/esco_skills_seed_v2.json (the original file is not changed)
Run:    python add_future_skills_to_seed.py
"""
import json
from collections import Counter

MIN_ROLES = 2   # use 1 to add more (about 186 skills), 3 to add fewer (about 10)

with open("data/future_roles.json", encoding="utf-8") as f:
    roles = json.load(f)["roles"]
with open("data/esco_skills_seed_expanded.json", encoding="utf-8") as f:
    seed = json.load(f)
have = {s["esco_id"] for s in seed["skills"]}

count, info = Counter(), {}
for r in roles:
    for s in r["skills"]:
        if s["relation"] == "essential" and s["esco_id"] not in have:
            count[s["esco_id"]] += 1
            info[s["esco_id"]] = s

added = 0
for esco_id, n in count.most_common():
    if n < MIN_ROLES:
        break
    s = info[esco_id]
    seed["skills"].append({
        "esco_id": esco_id,
        "name": s["name"],
        "type": s["skill_type"],
        "description": "",
        "categories": ["future_role_skill"],
    })
    added += 1

seed["note"] = f"v2: added {added} ESCO skills that are essential for several target roles (category=future_role_skill)"
with open("data/esco_skills_seed_v2.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=True, indent=1)   # pure ASCII on purpose
print(f"Added {added} skills. Seed now has {len(seed['skills'])} skills -> data/esco_skills_seed_v2.json")
