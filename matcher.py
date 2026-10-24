"""
matcher.py  —  未来岗位匹配(确定性算法,不用 LLM)
=====================================================
输入:
  1. profile:app.py 生成的 final_profile(用到 profile["skills"] 里的 esco_id 和 level)
  2. roles:data/future_roles.json 里的 roles 列表
  3. trend(可选):{esco_id: 数字},-1(下降) ~ +1(上升),需要和趋势层队友约定
输出:
  按 match_score 从高到低排序的列表,每个岗位包含:
    match_score(0-100)、essential_coverage(必需技能覆盖率)、
    matched / partial / gaps(技能差距明细)、explanation(一句话解释)、source

打分规则(全部可解释):
  对岗位的每个技能:  覆盖度 = min(你的等级 / 岗位要求等级, 1)   # 没有这个技能 = 0
  match_score = 所有技能 (权重 x 覆盖度) 之和 / 权重之和 x 100
  权重:必需技能 1.0,可选技能 0.5(来自 future_roles.json)
  趋势(可选):上升的技能权重变大,下降的变小,强度由 TREND_STRENGTH 控制
"""
import json

TREND_STRENGTH = 0.5   # 趋势对权重的影响程度。0 = 完全忽略趋势
MIN_WEIGHT = 0.1       # 权重最低不低于这个值,避免被趋势降到 0


def load_roles(path="data/future_roles.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["roles"]


def user_skill_levels(profile):
    """把用户技能整理成 {esco_id: level}。同一技能重复出现取最高等级;未映射的(esco_id 为空)跳过。"""
    levels = {}
    for s in profile.get("skills", []):
        eid = s.get("esco_id")
        if not eid:
            continue
        levels[eid] = max(levels.get(eid, 0), int(s.get("level", 0)))
    return levels


def score_role(role, levels, trend=None):
    total_w = 0.0
    got_w = 0.0
    matched, partial, gaps = [], [], []
    ess_total = ess_have = 0

    for sk in role["skills"]:
        w = sk["weight"]
        if trend and sk["esco_id"] in trend:
            w = max(MIN_WEIGHT, w * (1 + TREND_STRENGTH * trend[sk["esco_id"]]))

        need = sk["required_level"]
        have = levels.get(sk["esco_id"], 0)
        cov = min(have / need, 1.0) if need else 1.0

        total_w += w
        got_w += w * cov
        if sk["relation"] == "essential":
            ess_total += 1
            ess_have += 1 if cov >= 1.0 else 0

        item = {
            "esco_id": sk["esco_id"],
            "name": sk["name"],
            "relation": sk["relation"],
            "your_level": have,
            "required_level": need,
            "level_gap": max(need - have, 0),
            "priority": round(w * (1 - cov), 3),   # 越大越该优先学
        }
        if cov >= 1.0:
            matched.append(item)
        elif have > 0:
            partial.append(item)
            gaps.append(item)
        else:
            gaps.append(item)

    gaps.sort(key=lambda g: g["priority"], reverse=True)
    score = round(100 * got_w / total_w, 1) if total_w else 0.0
    ess_cov = round(100 * ess_have / ess_total, 1) if ess_total else 0.0

    explanation = (
        f"You fully meet {len(matched)} of {len(role['skills'])} skills "
        f"({ess_have} of {ess_total} essential). "
        f"{len(partial)} are partly covered and {len(gaps) - len(partial)} are missing."
    )
    return {
        "role_id": role["role_id"],
        "title": role["title"],
        "match_score": score,
        "essential_coverage": ess_cov,
        "essential_have": ess_have,         # 已具备的必需技能数(展示用)
        "essential_total": ess_total,       # 必需技能总数
        "matched": matched,
        "partial": partial,
        "gaps": gaps,                       # 差距明细,已按优先级排序
        "explanation": explanation,
        "source": role["source"],           # 每条推荐都带来源
        "sdg_tags": role.get("sdg_tags", []),
    }


def match_roles(profile, roles, trend=None, top_n=None):
    levels = user_skill_levels(profile)
    results = [score_role(r, levels, trend) for r in roles]
    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results[:top_n] if top_n else results


# ---------------- 自测:python matcher.py ----------------
if __name__ == "__main__":
    roles = load_roles()
    with open("data/occupation_templates.json", encoding="utf-8") as f:
        templates = json.load(f)["templates"]

    for tpl in templates:
        fake_profile = {"skills": [{"esco_id": s["esco_id"], "level": s["default_level"]}
                                   for s in tpl["skills"]]}
        print(f"\n=== 用户:{tpl['display_name']['en']} ===")
        for r in match_roles(fake_profile, roles, top_n=3):
            top_gap = ", ".join(g["name"] for g in r["gaps"][:3])
            print(f"  {r['match_score']:5.1f}  {r['title']:30s} 最该先补: {top_gap}")
