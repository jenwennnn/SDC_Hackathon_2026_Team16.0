"""Unit tests for the ShiftHappens calculation logic (no Streamlit needed).

Run from the repository root:
    python -m unittest discover tests
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # data files are read with paths relative to the repository root

import fairness  # noqa: E402
import signals_logic as sl  # noqa: E402
import trend_bridge as tb  # noqa: E402
from matcher import load_roles, match_roles, rank_by_future_fit  # noqa: E402
from pathway import build_pathway, load_courses  # noqa: E402


def data_entry_profile():
    """Profile built the same way as the 'Data Entry & Processing' template in the app."""
    with open("data/occupation_templates.json", encoding="utf-8") as f:
        templates = json.load(f)["templates"]
    tpl = next(t for t in templates if t["display_name"]["en"] == "Data Entry & Processing")

    def clean(text):
        return re.sub(r"\[cite:[^\]]*\]", "", text).replace("[UNSOURCED]", "").strip()

    tasks = [(clean(t["label"]["en"]), t.get("task_type")) for t in tpl["tasks"]]
    return {
        "skills": [{"name": s["name"], "esco_id": s["esco_id"], "mapped": True,
                    "level": s["default_level"]} for s in tpl["skills"]],
        "current_role": {
            "title": "Data Entry & Processing",
            "tasks": [label for label, _ in tasks],
            "task_details": [{"label": label, "task_type": tt} for label, tt in tasks],
        },
        "constraints": {"hours_per_week": 5, "budget": "free", "timeline_months": 6},
    }


class TestSignals(unittest.TestCase):
    def test_signals_file_is_valid(self):
        data = sl.load_signals()  # raises if the file has problems
        self.assertEqual(sl.validate_signals(data), [])
        self.assertGreaterEqual(len(sl.batch_ids(data)), 2)

    def test_every_batch_has_source_date_and_synthetic_flag(self):
        for batch in sl.load_signals()["batches"]:
            meta = batch["meta"]
            self.assertTrue(meta["source_name"])
            self.assertTrue(meta["data_date"])
            self.assertIsInstance(meta["is_synthetic"], bool)

    def test_basket_rule(self):
        # pressure = exposure x (1 - augment) / 2
        self.assertEqual(sl.task_basket(0.9, -0.5)[0], "take_over")  # pressure 0.675
        self.assertEqual(sl.task_basket(0.6, 0.5)[0], "assist")      # pressure 0.15, exposure 0.6
        self.assertEqual(sl.task_basket(0.2, 0.0)[0], "human")       # low exposure
        self.assertEqual(sl.task_basket(None, 0.0)[0], "unknown")


class TestDemoFlow(unittest.TestCase):
    """The numbers shown in the demo video for the Data Entry template."""

    @classmethod
    def setUpClass(cls):
        cls.profile = data_entry_profile()
        cls.data = sl.load_signals()
        cls.latest = sl.batch_ids(cls.data)[-1]
        cls.trends = tb.build_trends(cls.data, tb.load_skill_map(), cls.latest)
        cls.roles = load_roles()

    def counts(self, scenario):
        rows = sl.build_my_day(self.profile["current_role"]["task_details"],
                               self.data, self.latest, scenario)
        return [sum(r["basket"] == b for r in rows) for b in sl.BASKETS]

    def test_day_view_steady_and_rapid(self):
        self.assertEqual(self.counts("steady"), [5, 1, 3])
        self.assertEqual(self.counts("rapid"), [6, 3, 0])

    def test_ranking_has_ten_roles_with_scores(self):
        ranked = rank_by_future_fit(match_roles(self.profile, self.roles,
                                                trend=self.trends["steady"]), 0.5)
        self.assertEqual(len(ranked), 10)
        fits = [r["future_fit"] for r in ranked]
        self.assertEqual(fits, sorted(fits, reverse=True))

    def test_trend_weight_changes_the_ranking(self):
        matches = match_roles(self.profile, self.roles, trend=self.trends["steady"])
        skills_first = [r["title"] for r in rank_by_future_fit(matches, 0.0)]
        market_first = [r["title"] for r in rank_by_future_fit(matches, 1.0)]
        self.assertNotEqual(skills_first, market_first)

    def test_fairness_all_tests_pass(self):
        result = fairness.check_fairness(self.profile, self.roles, self.trends["steady"], 0.5)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["tests"]), 14)

    def test_free_plan_costs_nothing(self):
        ranked = rank_by_future_fit(match_roles(self.profile, self.roles,
                                                trend=self.trends["steady"]), 0.5)
        plan = build_pathway(ranked[0], self.profile["constraints"], load_courses())
        self.assertEqual(plan["total_cost_myr"], 0)
        self.assertLessEqual(plan["covered_count"], plan["target_count"])


if __name__ == "__main__":
    unittest.main()
