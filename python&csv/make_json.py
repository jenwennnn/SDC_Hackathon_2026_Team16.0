import pandas as pd
import json

print("Reading selected.csv...")
sel = pd.read_csv("selected.csv")

seed = [
    {
        "esco_id": row["conceptUri"],
        "name": row["preferredLabel"],
        "type": row["skillType"],
        # 增加 pd.notna 判断，防止空值转换报错
        "description": str(row["description"])[:200] if pd.notna(row["description"]) else ""
    }
    for _, row in sel.iterrows()
]

meta = {
    "source": "ESCO (European Skills, Competences, Qualifications and Occupations)",
    "version": "1.1.2", 
    "downloaded": "2026-10-23",
    "skills": seed,
}

# 核心防坑：必须显式声明 encoding="utf-8"
with open("esco_skills_seed.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print(f"Success! Generated esco_skills_seed.json with {len(seed)} skills.")