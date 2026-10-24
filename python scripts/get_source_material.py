import pandas as pd

occ = pd.read_csv("esco/occupations_en.csv")
sel = pd.read_csv("outputs/occupations_selected.csv")

print(occ.columns.tolist())   # 先确认列名,下面的列名按实际改

# 用职业ID匹配,取出名称和描述
merged = sel.merge(occ, left_on="occupation_uri", right_on="conceptUri", how="left")

with open("outputs/source_material.txt", "w", encoding="utf-8") as f:
    for cat, group in merged.groupby("category"):
        f.write(f"=== CATEGORY: {cat} ===\n")
        for _, r in group.iterrows():
            f.write(f"[{r['preferredLabel']}]\n{r['description']}\n\n")