import json
seed = {s["esco_id"] for s in json.load(open("data/esco_skills_seed.json"))["skills"]}
tpl = json.load(open("data/occupation_templates.json"))
bad = [(t["template_id"], s["name"]) for t in tpl["templates"] for s in t["skills"] if s["esco_id"] not in seed]
print("The skills that not in seeds:", bad or "No, passed.")