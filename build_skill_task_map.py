"""
build_skill_task_map.py
-----------------------
Maps every ESCO skill in data/future_roles.json to ONE of the 12 task types
used by data/signals.json, so trend signals (per task type) can be turned
into per-skill trend scores for the matcher (per esco_id).

Method: simple keyword rules, checked in order; the first rule that matches
the skill name wins. Skills that match no rule get task_type = null and
receive NO trend adjustment (score 0).

This is a TEAM ASSUMPTION, not an official ESCO mapping. The output file is
marked draft_needs_human_review and records which keyword matched each skill,
so a reviewer can check and correct it.

How to run (from the project folder):
    python build_skill_task_map.py
Output:
    data/skill_task_map.json
"""

import json
import os
from datetime import date

ROLES_PATH = os.path.join("data", "future_roles.json")
OUTPUT_PATH = os.path.join("data", "skill_task_map.json")

# Ordered rules: (task_type, [keywords]). Keywords are matched against the
# lower-case skill name. Order matters: earlier rules win.
RULES = [
    ("data_entry", [
        "process data", "data processing techniques", "digital data processing",
        "maintain customer records", "keep records", "records of customer",
        "incident reporting records", "tabulate",
    ]),
    ("calculation_reconciliation", [
        "accounting", "ledger", "audit", "tax", "financial statements",
        "budget", "expenditure", "cost", "calculation", "manage accounts",
    ]),
    ("scheduling_coordination", [
        "schedule", "fix meetings", "plan shifts", "event management",
        "project management", "special events",
    ]),
    ("document_processing", [
        "documentation types", "information categorisation", "information structure",
        "manage contracts", "digital curation", "legal case management",
        "information extraction",
    ]),
    ("reporting_writing", [
        "report", "write", "draft", "document", "publication", "papers",
        "present",
    ]),
    ("data_analysis", [
        "analys", "analytic", "statistic", "mining", "model", "big data",
        "quantitative", "forecast", "interpret", "data science", "visualisation",
        "query", "database", "data quality", "cleansing", "market research",
        "survey", "business intelligence", "trend", "empirical",
    ]),
    ("customer_communication", [
        "customer", "client", "enquir", "complaint", "guest", "sales pitch",
    ]),
    ("relationship_building", [
        "relationship", "network", "trust", "liaise", "shareholder",
        "mentor", "communit",
    ]),
    ("content_creation", [
        "content", "social media", "brand", "advertis", "campaign",
        "email marketing", "digital media", "search engine", "online ads",
        "pay-per-click", "interactive media",
    ]),
    ("internal_communication", [
        "cooperat", "internal communication", "collaborat", "colleagues",
        "cross-department", "support managers",
    ]),
    ("decision_judgement", [
        "decision", "strateg", "advise", "risk", "polic", "compliance",
        "legal", "manage staff", "supervise", "objectives", "ethic",
        "solutions to problems", "address problems",
    ]),
]


def classify(skill_name):
    """Return (task_type, matched_keyword) or (None, None)."""
    name = skill_name.lower()
    for task_type, keywords in RULES:
        for kw in keywords:
            if kw in name:
                return task_type, kw
    return None, None


def main():
    with open(ROLES_PATH, "r", encoding="utf-8") as f:
        roles = json.load(f)["roles"]

    skills = {}
    for role in roles:
        for s in role["skills"]:
            skills[s["esco_id"]] = s["name"]

    mapping = {}
    for esco_id, name in sorted(skills.items(), key=lambda kv: kv[1].lower()):
        task_type, keyword = classify(name)
        mapping[esco_id] = {
            "name": name,
            "task_type": task_type,
            "matched_keyword": keyword,
        }

    mapped = sum(1 for m in mapping.values() if m["task_type"])
    output = {
        "status": "draft_needs_human_review",
        "method": "keyword_rules_v1 (see build_skill_task_map.py)",
        "note": ("Team assumption, not an official ESCO mapping. Skills with "
                 "task_type null receive no trend adjustment."),
        "generated": date.today().isoformat(),
        "skill_count": len(mapping),
        "mapped_count": mapped,
        "skills": mapping,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=True)
    print(f"Wrote {OUTPUT_PATH}: {mapped} of {len(mapping)} skills mapped to a task type.")


if __name__ == "__main__":
    main()
