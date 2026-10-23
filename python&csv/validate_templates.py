import argparse
import json
import re
import sys
import sys
import io
from itertools import combinations

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ---------- 规则(想改规则只需要改这里) ----------
ALLOWED_TASK_TYPES = {
    "data_entry", "document_processing", "customer_communication",
    "internal_communication", "scheduling_coordination", "reporting_writing",
    "calculation_reconciliation", "data_analysis", "content_creation",
    "physical_or_manual", "decision_judgement", "relationship_building",
}
ALLOWED_SKILL_GROUPS = {"core", "soft", "digital"}
ALLOWED_STATUS = {"draft_needs_human_review", "reviewed"}
TASKS_RANGE = (8, 15)      # 超出范围只警告
SKILLS_RANGE = (10, 14)
MAX_LABEL_WORDS = 15
OVERLAP_WARN = 0.6         # 两个模板技能重合度超过此值则警告(区分度不足)
VAGUE_PHRASES = ["various", "general tasks", "daily tasks", "other duties",
                 "as needed", "misc", "etc", "handle matters", "day-to-day"]
# 数字、百分号、货币符号:任务文字里不应出现统计数据
STAT_PATTERN = re.compile(r"\d|%|\bRM\b|\$|percent|per cent", re.IGNORECASE)


class Report:
    def __init__(self):
        self.errors, self.warnings, self.infos = [], [], []

    def error(self, msg): self.errors.append(msg)
    def warn(self, msg): self.warnings.append(msg)
    def info(self, msg): self.infos.append(msg)


def load_json(path, label, rep):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        rep.error(f"{label}: 找不到文件 {path}")
    except json.JSONDecodeError as e:
        rep.error(f"{label}: JSON 格式不合法 (第{e.lineno}行, 第{e.colno}列): {e.msg}")
    return None


def load_seed(path, rep):
    """返回 {esco_id: name};兼容 {"skills":[...]} 或直接 [...]"""
    data = load_json(path, "seed文件", rep)
    if data is None:
        return None
    skills = data.get("skills") if isinstance(data, dict) else data
    if not isinstance(skills, list):
        rep.error("seed文件: 找不到技能列表 (应为 {\"skills\": [...]} 或 [...])")
        return None
    seed = {}
    for i, s in enumerate(skills):
        sid, name = s.get("esco_id"), s.get("name")
        if not sid or not name:
            rep.error(f"seed文件: 第{i+1}条缺少 esco_id 或 name")
            continue
        if not str(sid).startswith("http"):
            rep.warn(f"seed文件: '{name}' 的 esco_id 不是完整网址: {sid}")
        if "TODO_VERIFY" in str(sid):
            rep.warn(f"seed文件: '{name}' 的 ID 仍是 TODO_VERIFY")
        if sid in seed:
            rep.warn(f"seed文件: 重复的 esco_id: {sid}")
        seed[sid] = name
    rep.info(f"seed文件: 读取到 {len(seed)} 条技能")
    return seed


def is_nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def check_template(t, idx, seed, rep, all_status):
    tid = t.get("template_id") or f"(第{idx+1}个模板)"
    p = f"[{tid}]"

    # --- 必填字段 ---
    for key in ["template_id", "display_name", "typical_titles", "isco_codes",
                "tasks", "skills", "grounding_notes", "review"]:
        if key not in t:
            rep.error(f"{p} 缺少字段: {key}")
    if not is_nonempty_str(t.get("template_id")):
        rep.error(f"{p} template_id 为空")

    dn = t.get("display_name", {})
    if not isinstance(dn, dict) or not is_nonempty_str(dn.get("en")):
        rep.error(f"{p} display_name.en 不能为空")

    titles = t.get("typical_titles")
    if not isinstance(titles, list) or not titles:
        rep.error(f"{p} typical_titles 应是非空列表")

    # --- ISCO ---
    for code in t.get("isco_codes", []) or []:
        if code == "TODO_VERIFY":
            rep.info(f"{p} isco_codes 仍是 TODO_VERIFY(冷启动流程暂不影响)")
        elif not re.fullmatch(r"\d{1,4}", str(code)):
            rep.warn(f"{p} isco_codes 格式异常: {code}")

    # --- 任务 ---
    tasks = t.get("tasks", []) or []
    if not (TASKS_RANGE[0] <= len(tasks) <= TASKS_RANGE[1]):
        rep.warn(f"{p} 任务数量 {len(tasks)},建议 {TASKS_RANGE[0]}-{TASKS_RANGE[1]} 条")
    seen_task_ids, type_counts = set(), {}
    for j, task in enumerate(tasks):
        tp = f"{p} 任务{j+1}"
        tk_id = task.get("task_id")
        if not is_nonempty_str(tk_id):
            rep.error(f"{tp}: task_id 为空")
        elif tk_id in seen_task_ids:
            rep.error(f"{tp}: task_id 重复: {tk_id}")
        seen_task_ids.add(tk_id)

        label = (task.get("label") or {}).get("en", "")
        if not is_nonempty_str(label):
            rep.error(f"{tp} ({tk_id}): label.en 为空")
        else:
            body = label.replace("[UNSOURCED]", "").strip()
            if "[UNSOURCED]" in label:
                rep.warn(f"{tp} ({tk_id}): 标记为 [UNSOURCED],需决定保留/改写/删除 -> \"{body}\"")
            if STAT_PATTERN.search(body):
                rep.error(f"{tp} ({tk_id}): 任务文字里出现数字/百分比/货币,疑似统计数据 -> \"{body}\"")
            if len(body.split()) > MAX_LABEL_WORDS:
                rep.warn(f"{tp} ({tk_id}): 超过 {MAX_LABEL_WORDS} 个词,可能包含多项活动 -> \"{body}\"")
            if body and not body[0].isupper():
                rep.warn(f"{tp} ({tk_id}): 建议以大写动词开头 -> \"{body}\"")
            low = body.lower()
            for ph in VAGUE_PHRASES:
                if re.search(rf"\b{re.escape(ph)}\b", low):
                    rep.warn(f"{tp} ({tk_id}): 含模糊用语 '{ph}' -> \"{body}\"")
                    break

        tt = task.get("task_type")
        if tt not in ALLOWED_TASK_TYPES:
            rep.error(f"{tp} ({tk_id}): task_type '{tt}' 不在允许列表里")
        else:
            type_counts[tt] = type_counts.get(tt, 0) + 1

        if task.get("exposure_hint") is not None:
            rep.error(f"{tp} ({tk_id}): exposure_hint 必须是 null(AI暴露度需有来源,另行处理)")

    # 任务类型多样性:不应全是常规任务,也不应全是判断任务
    if tasks and len(type_counts) < 3:
        rep.warn(f"{p} 任务类型只有 {len(type_counts)} 种,缺少多样性: {sorted(type_counts)}")
    human_types = {"decision_judgement", "relationship_building", "internal_communication", "customer_communication"}
    if tasks and not (set(type_counts) & human_types):
        rep.warn(f"{p} 没有任何沟通/判断/关系类任务,可能让职业显得过于危险")

    # --- 技能 ---
    skills = t.get("skills", []) or []
    if not (SKILLS_RANGE[0] <= len(skills) <= SKILLS_RANGE[1]):
        rep.warn(f"{p} 技能数量 {len(skills)},建议 {SKILLS_RANGE[0]}-{SKILLS_RANGE[1]} 条")
    seen_skill_ids = set()
    for j, sk in enumerate(skills):
        sp = f"{p} 技能{j+1}"
        sid, name = sk.get("esco_id"), sk.get("name")
        if not is_nonempty_str(sid):
            rep.error(f"{sp}: esco_id 为空 (名称: {name})")
        else:
            if sid in seen_skill_ids:
                rep.error(f"{sp}: 技能重复: {name}")
            seen_skill_ids.add(sid)
            if seed is not None:
                if sid not in seed:
                    rep.error(f"{sp}: esco_id 不在seed文件里(疑似AI编造) -> {name} | {sid}")
                elif seed[sid] != name:
                    rep.error(f"{sp}: 名称与seed不一致 -> 模板: '{name}' / seed: '{seed[sid]}'")
        lvl = sk.get("default_level")
        if not (isinstance(lvl, int) and not isinstance(lvl, bool) and 1 <= lvl <= 5):
            rep.error(f"{sp}: default_level 应为 1-5 的整数,实际: {lvl!r}")
        if sk.get("skill_group") not in ALLOWED_SKILL_GROUPS:
            rep.error(f"{sp}: skill_group '{sk.get('skill_group')}' 应为 {sorted(ALLOWED_SKILL_GROUPS)} 之一")

    # --- grounding_notes ---
    gn = t.get("grounding_notes")
    if not is_nonempty_str(gn):
        rep.error(f"{p} grounding_notes 为空(任务来源必须可追溯)")
    elif "%" in gn:
        rep.warn(f"{p} grounding_notes 含 % ,请确认不是编造的统计")

    # --- review 区块 ---
    rv = t.get("review") or {}
    if all_status == "reviewed":
        if not rv.get("reviewed_by") or not rv.get("reviewed_at"):
            rep.error(f"{p} 文件 status 为 reviewed,但 review.reviewed_by / reviewed_at 未填写")
    return {s for s in seen_skill_ids}


def main():
    ap = argparse.ArgumentParser(description="校验 occupation_templates.json")
    ap.add_argument("--templates", default="data/occupation_templates.json")
    ap.add_argument("--seed", default="data/esco_skills_seed.json")
    args = ap.parse_args()

    rep = Report()
    seed = load_seed(args.seed, rep)
    data = load_json(args.templates, "模板文件", rep)

    if data is not None:
        if not isinstance(data, dict) or not isinstance(data.get("templates"), list):
            rep.error("模板文件: 顶层应为对象且包含 templates 列表")
        else:
            status = data.get("status")
            if status not in ALLOWED_STATUS:
                rep.error(f"status 应为 {sorted(ALLOWED_STATUS)} 之一,实际: {status!r}")
            elif status == "draft_needs_human_review":
                rep.info("status = draft_needs_human_review(人工审核完成后改为 reviewed)")
            if "version" not in data:
                rep.warn("缺少顶层字段 version")

            # 全文扫描 JSON 文本里的 TODO / 占位符
            raw = json.dumps(data, ensure_ascii=False)
            if re.search(r"<必须|PASTE|\[fill", raw, re.IGNORECASE):
                rep.error("文件里残留占位符 (如 <必须来自seed文件> 或 PASTE)")

            ids, skill_sets = set(), {}
            for i, t in enumerate(data["templates"]):
                tid = t.get("template_id")
                if tid in ids:
                    rep.error(f"template_id 重复: {tid}")
                ids.add(tid)
                skill_sets[tid or f"#{i+1}"] = check_template(t, i, seed, rep, status)

            # 模板之间的区分度
            for (a, sa), (b, sb) in combinations(skill_sets.items(), 2):
                if sa and sb:
                    jac = len(sa & sb) / len(sa | sb)
                    if jac > OVERLAP_WARN:
                        rep.warn(f"模板 {a} 与 {b} 技能重合度 {jac:.0%},区分度不足(请检查是否都塞了同样的通用数字技能)")

            miss = data.get("missing_skills_suggestions") or []
            if miss:
                rep.info(f"missing_skills_suggestions 共 {len(miss)} 条,待到ESCO里查找: {miss}")

            rep.info(f"共检查 {len(data['templates'])} 个模板")

    # ---------- 输出 ----------
    print("=" * 60)
    print(" occupation_templates 校验报告")
    print("=" * 60)
    for title, items, mark in [("ERRORS 错误(必须修)", rep.errors, "✗"),
                               ("WARNINGS 警告(建议处理)", rep.warnings, "!"),
                               ("INFO 信息", rep.infos, "·")]:
        print(f"\n{title}: {len(items)}")
        for m in items:
            print(f"  {mark} {m}")
    print("\n" + "-" * 60)
    if rep.errors:
        print(f"结果: 未通过 ({len(rep.errors)} 个错误, {len(rep.warnings)} 个警告)")
        sys.exit(1)
    print(f"结果: 通过 ({len(rep.warnings)} 个警告)")
    sys.exit(0)


if __name__ == "__main__":
    main()