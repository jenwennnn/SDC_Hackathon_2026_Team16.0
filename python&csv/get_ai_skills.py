import pandas as pd

print("Hunting for AI-era skills...")
skills = pd.read_csv("skills_en.csv")

# 我们专门搜索 AI、数据分析和数字素养相关的关键词
ai_keywords = [
    "artificial intelligence", "data analysis", 
    "digital literacy", "machine learning", "data analytics"
]

mask = skills["preferredLabel"].str.lower().str.contains("|".join(ai_keywords), na=False)
ai_candidates = skills[mask][["conceptUri", "preferredLabel", "skillType", "description"]]

# 打印出最相关的 15 个让你挑选
print("\n=== AI & Data Skills Candidates ===")
print(ai_candidates["preferredLabel"].head(15).to_string())

# 把这些 AI 技能单独存一个文件方便你挑选
ai_candidates.head(15).to_csv("ai_skills_pool.csv", index=False)
print("\nSaved 15 AI skills to ai_skills_pool.csv!")