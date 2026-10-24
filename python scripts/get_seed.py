import pandas as pd

print("Reading ESCO data files...")
occ = pd.read_csv("occupations_en.csv")
rel = pd.read_csv("occupationSkillRelations_en.csv")
skills = pd.read_csv("skills_en.csv")

targets = [
    "administrative assistant", "data entry clerk", 
    "customer service representative", "retail sales", 
    "bookkeeper", "accounting clerk", "finance clerk",
    "copywriter", "marketing assistant", 
    "warehouse clerk", "logistics clerk"
]
mask = occ["preferredLabel"].str.lower().str.contains("|".join(targets), na=False)
matched_occ = occ[mask]

print(f"Found {len(matched_occ)} related occupations.")

chosen_occ = matched_occ["conceptUri"].tolist()

r = rel[rel["occupationUri"].isin(chosen_occ)]
r = r[r["relationType"] == "essential"]

top = r["skillUri"].value_counts().head(55)

result = skills[skills["conceptUri"].isin(top.index)]
final_data = result[["conceptUri", "preferredLabel", "skillType", "description"]]

final_data.to_csv("candidates.csv", index=False)
print(f"Successfully extracted {len(final_data)} core skills! Saved as candidates.csv.")