"""
build_future_roles.py
---------------------
作用:从 ESCO 的 CSV 自动生成 data/future_roles.json(岗位 + 每个岗位的技能)。
全程不手打、不编造:岗位名、技能名、技能ID、岗位描述 全部来自 ESCO CSV。

输入(都放在 data/ 文件夹):
  - data/occupations_en.csv
  - data/occupationSkillRelations_en.csv
  - data/esco_skills_seed_expanded.json  (或 esco_skills_seed.json)
  - data/occupation_templates.json
输出:
  - data/future_roles.json

运行:  python build_future_roles.py
"""
import csv
import json
import os
import sys
from datetime import date

DATA_DIR = "data"

# ============ 你唯一需要改的地方:目标岗位名单 ============
# 必须和 ESCO 里的 preferredLabel 完全一致(大小写不限)。
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
# ===========================================================

# 团队假设(会写进 JSON,答辩时要说明):ESCO 没有熟练度等级,
# 所以必需技能要求 3 级,可选技能要求 2 级。
LEVEL_BY_RELATION = {"essential": 3, "optional": 2}
WEIGHT_BY_RELATION = {"essential": 1.0, "optional": 0.5}


def find_file(*names):
    for n in names:
        p = os.path.join(DATA_DIR, n)
        if os.path.exists(p):
            return p
    sys.exit(f"找不到文件:{names},请确认它们放在 {DATA_DIR}/ 文件夹里。")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    occ_rows = read_csv(find_file("occupations_en.csv"))
    rel_rows = read_csv(find_file("occupationSkillRelations_en.csv"))
    seed = json.load(open(find_file("esco_skills_seed_expanded.json",
                                    "esco_skills_seed.json"), encoding="utf-8"))
    templates = json.load(open(find_file("occupation_templates.json"),
                               encoding="utf-8"))["templates"]

    seed_ids = {s["esco_id"] for s in seed["skills"]}
    tpl_skill_ids = {t["template_id"]: {s["esco_id"] for s in t["skills"]}
                     for t in templates}

    # 按名字找岗位(必须刚好找到 1 个)
    by_label = {}
    for row in occ_rows:
        by_label.setdefault(row["preferredLabel"].strip().lower(), []).append(row)

    roles = []
    print(f"{'岗位':34s} {'技能数':>6s} {'必需':>5s} {'与seed重合':>9s}  相关现职模板")
    for title in TARGET_ROLES:
        hits = by_label.get(title.strip().lower(), [])
        if len(hits) != 1:
            sys.exit(f"岗位 '{title}' 在 ESCO 里找到 {len(hits)} 个(应该是 1 个)。"
                     "请检查拼写,或把它从名单里删掉。")
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
        # 必需技能排前面
        skills.sort(key=lambda s: (s["relation"] != "essential", s["name"]))

        role_skill_ids = {s["esco_id"] for s in skills}
        related = [tid for tid, ids in tpl_skill_ids.items()
                   if len(ids & role_skill_ids) >= 2]
        overlap = sum(1 for s in skills if s["in_seed"])
        n_ess = sum(1 for s in skills if s["relation"] == "essential")
        print(f"{occ['preferredLabel']:34s} {len(skills):6d} {n_ess:5d} {overlap:9d}  {related}")

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
        "esco_version_note": f"seed 文件标注为 {seed.get('version')},请核实 CSV 版本是否一致",
        "generated": date.today().isoformat(),
        "status": "draft_needs_human_review",
        "level_note": "ESCO 不提供熟练度等级。required_level 是团队假设:必需=3,可选=2。",
        "roles": roles,
    }
    out_path = os.path.join(DATA_DIR, "future_roles.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n完成!已生成 {out_path},共 {len(roles)} 个岗位。")


if __name__ == "__main__":
    main()
