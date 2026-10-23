import pandas as pd
import sys
import os
import json

# Ensure output directories exist
os.makedirs("outputs", exist_ok=True)
os.makedirs("data", exist_ok=True)

# Define categories and their target keywords
CATEGORIES = {
    "admin_clerical": ["administrative assistant", "office clerk", "secretary", "receptionist"],
    "data_entry": ["data entry clerk", "data processing"],
    "customer_service": ["customer service", "call centre", "helpdesk"],
    "accounting_support": ["bookkeeper", "accounting clerk", "payroll clerk"],
    "content_marketing_support": ["copywriter", "content", "marketing assistant", "social media"]
}

def mode_occupations():
    print("--- MODE 1: FINDING OCCUPATION CANDIDATES ---")
    file_path = "esco/occupations_en.csv"
    
    try:
        df_occ = pd.read_csv(file_path, low_memory=False)
        print(f"Loaded {len(df_occ)} total occupations from {file_path}")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # Handle NaNs in search columns
    df_occ['preferredLabel'] = df_occ['preferredLabel'].fillna('')
    df_occ['altLabels'] = df_occ['altLabels'].fillna('')

    results = []
    
    for category, keywords in CATEGORIES.items():
        # Create a boolean mask to find rows where preferredLabel OR altLabels contain any keyword
        mask = pd.Series(False, index=df_occ.index)
        for kw in keywords:
            kw_lower = kw.lower()
            mask = mask | df_occ['preferredLabel'].str.lower().str.contains(kw_lower, na=False)
            mask = mask | df_occ['altLabels'].str.lower().str.contains(kw_lower, na=False)
        
        cat_matches = df_occ[mask]
        print(f"[{category}] found {len(cat_matches)} candidate occupations.")
        
        for _, row in cat_matches.iterrows():
            results.append({
                "category": category,
                "occupation_uri": row['conceptUri'],
                "occupation_label": row['preferredLabel'],
                "isco_group": row.get('iscoGroup', '') # use .get to prevent crashes if column is missing
            })
            
    out_df = pd.DataFrame(results)
    out_path = "outputs/occupation_candidates.csv"
    out_df.to_csv(out_path, index=False)
    print(f"\nSUCCESS: Wrote {len(out_df)} candidate rows to {out_path}")
    print("--> NEXT STEP: Review this file by hand, delete wrong occupations, and save as 'outputs/occupations_selected.csv'.")

def mode_skills():
    print("--- MODE 2: EXTRACTING ESSENTIAL SKILLS ---")
    sel_occ_path = "outputs/occupations_selected.csv"
    rel_path = "esco/occupationSkillRelations_en.csv"
    skills_path = "esco/skills_en.csv"
    
    if not os.path.exists(sel_occ_path):
        print(f"ERROR: Cannot find {sel_occ_path}. Did you complete Mode 1 and review the file?")
        return

    # 1. Read selected occupations
    df_sel_occ = pd.read_csv(sel_occ_path)
    print(f"Loaded {len(df_sel_occ)} approved occupations.")

    # 2. Read relations and filter for 'essential'
    df_rel = pd.read_csv(rel_path, low_memory=False)
    df_rel['relationType'] = df_rel['relationType'].fillna('')
    df_rel_ess = df_rel[df_rel['relationType'].str.lower() == 'essential']
    print(f"Loaded {len(df_rel)} skill relations. Filtered down to {len(df_rel_ess)} essential relations.")

    # 3. Read skills to get labels, types, and descriptions
    df_skills = pd.read_csv(skills_path, low_memory=False)
    print(f"Loaded {len(df_skills)} total skills.")

    # 4. Merge data
    # Join selected occupations with their essential skills
    merged = df_sel_occ.merge(df_rel_ess, left_on='occupation_uri', right_on='occupationUri', how='inner')
    # Join the actual skill details
    merged = merged.merge(df_skills, left_on='skillUri', right_on='conceptUri', how='inner')
    print(f"Mapped {len(merged)} total skill occurrences across all selected occupations.")

    # 5. Group by category and skill to count frequencies
    skill_counts = merged.groupby(
        ['category', 'skillUri', 'preferredLabel', 'skillType', 'description'], dropna=False
    ).size().reset_index(name='frequency')

    # Rename columns to match requirements
    skill_counts = skill_counts.rename(columns={
        'skillUri': 'skill_uri',
        'preferredLabel': 'skill_label',
        'skillType': 'skill_type',
        'description': 'short_description'
    })
    
    # Truncate description to 200 chars to keep it brief and handle NaNs
    skill_counts['short_description'] = skill_counts['short_description'].fillna('').astype(str).str[:200]

    # Keep top 30 per category
    final_skills = []
    for cat in CATEGORIES.keys():
        cat_skills = skill_counts[skill_counts['category'] == cat]
        cat_top30 = cat_skills.sort_values(by='frequency', ascending=False).head(30)
        final_skills.append(cat_top30)
        print(f"[{cat}] identified top {len(cat_top30)} skills.")

    df_final_skills = pd.concat(final_skills, ignore_index=True)
    out_skills_path = "outputs/skill_candidates.csv"
    df_final_skills.to_csv(out_skills_path, index=False)
    print(f"\nSUCCESS: Wrote {len(df_final_skills)} candidate skills to {out_skills_path}")
    print("--> NEXT STEP: Review this file by hand, delete wrong skills, and save as 'outputs/skills_selected.csv'.")

    # Cross-Category Core Skills
    cross_cat = df_final_skills.groupby(['skill_uri', 'skill_label']).size().reset_index(name='category_count')
    core_skills = cross_cat[cross_cat['category_count'] >= 3].sort_values(by='category_count', ascending=False)
    
    print("\n--- COMMON CORE SKILLS (Found in 3+ categories) ---")
    if len(core_skills) > 0:
        for _, row in core_skills.iterrows():
            print(f"- {row['skill_label']} ({row['category_count']} categories)")
    else:
        print("No skills found appearing in 3 or more categories.")

def mode_seed():
    print("--- MODE 3: GENERATING JSON SEED FILE ---")
    sel_skills_path = "outputs/skills_selected.csv"
    
    if not os.path.exists(sel_skills_path):
        print(f"ERROR: Cannot find {sel_skills_path}. Did you complete Mode 2 and review the file?")
        return

    df_sel_skills = pd.read_csv(sel_skills_path)
    print(f"Loaded {len(df_sel_skills)} approved skill rows.")
    
    # Ask for metadata
    version = input("Enter ESCO version (e.g., v1.1.1): ")
    downloaded = input("Enter download date (e.g., 2024-05-10): ")
    
    # Group categories by skill (since a skill might be in multiple categories now)
    grouped = df_sel_skills.groupby(['skill_uri', 'skill_label', 'skill_type', 'short_description'], dropna=False)
    
    skills_json = []
    for name, group in grouped:
        skill_uri, skill_label, skill_type, desc = name
        categories = group['category'].dropna().unique().tolist()
        
        skills_json.append({
            "esco_id": str(skill_uri),
            "name": str(skill_label),
            "type": str(skill_type) if pd.notna(skill_type) else "",
            "description": str(desc) if pd.notna(desc) else "",
            "categories": categories
        })

    output_data = {
        "source": "ESCO",
        "version": version,
        "downloaded": downloaded,
        "skills": skills_json
    }

    out_json_path = "data/esco_skills_seed.json"
    with open(out_json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4)
        
    print(f"\nSUCCESS: Generated JSON seed with {len(skills_json)} unique skills at {out_json_path}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        mode_occupations()
    elif len(sys.argv) == 2 and sys.argv[1] == "skills":
        mode_skills()
    elif len(sys.argv) == 2 and sys.argv[1] == "seed":
        mode_seed()
    else:
        print("Usage:")
        print("  python build_seed.py         (Runs mode 1: Find Occupations)")
        print("  python build_seed.py skills  (Runs mode 2: Extract Skills)")
        print("  python build_seed.py seed    (Runs mode 3: Generate JSON Seed)")