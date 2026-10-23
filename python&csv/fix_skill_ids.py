#!/usr/bin/env python3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import json
import pandas as pd

SEED_PATH = "data/esco_skills_seed.json"
TPL_PATH = "data/occupation_templates.json"
ESCO_CSV = "esco/skills_en.csv"   # 列名以你实际文件为准

seed = json.load(open(SEED_PATH, encoding="utf-8"))
tpl = json.load(open(TPL_PATH, encoding="utf-8"))
esco = pd.read_csv(ESCO_CSV)
print("ESCO列名:", esco.columns.tolist())

norm = lambda s: str(s).strip().lower()
seed_by_name = {norm(s["name"]): s for s in seed["skills"]}
esco_by_name = {}
for _, r in esco.iterrows():
    esco_by_name.setdefault(norm(r["preferredLabel"]), r)

stats = {"ok_in_seed": 0, "id_fixed_from_seed": 0, "added_from_esco": 0, "dropped": []}

for t in tpl["templates"]:
    kept = []
    for sk in t["skills"]:
        key = norm(sk["name"])
        if key in seed_by_name:                      # 1) seed里有这个名字
            real = seed_by_name[key]
            if sk["esco_id"] == real["esco_id"]:
                stats["ok_in_seed"] += 1
            else:
                stats["id_fixed_from_seed"] += 1
            sk["esco_id"], sk["name"] = real["esco_id"], real["name"]
            kept.append(sk)
        elif key in esco_by_name:                    # 2) ESCO原始文件里有
            r = esco_by_name[key]
            entry = {
                "esco_id": r["conceptUri"],
                "name": r["preferredLabel"],
                "type": r.get("skillType", ""),
                "description": str(r.get("description", ""))[:200],
                "categories": [t["template_id"]],
            }
            seed["skills"].append(entry)
            seed_by_name[key] = entry
            sk["esco_id"], sk["name"] = entry["esco_id"], entry["name"]
            stats["added_from_esco"] += 1
            kept.append(sk)
        else:                                        # 3) 两边都没有 -> 移除并报告
            stats["dropped"].append((t["template_id"], sk["name"]))
    t["skills"] = kept

json.dump(tpl, open("data/occupation_templates.fixed.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
json.dump(seed, open("data/esco_skills_seed.expanded.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

print("\n已在seed且ID正确:", stats["ok_in_seed"])
print("名称在seed里,ID已更正:", stats["id_fixed_from_seed"])
print("从ESCO补进seed:", stats["added_from_esco"])
print("两边都查不到(已从模板移除):", len(stats["dropped"]))
for d in stats["dropped"]:
    print("   -", d)
print("\nseed现在共", len(seed["skills"]), "条技能")