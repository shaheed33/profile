"""Checks on the state budget data build. Run: python -m unittest discover -s tests -p 'test_state_budget.py'"""
import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_state_budget.py"
RAW = ROOT / "data" / "raw" / "state_budgets_2026-27.json"


def build(raw_obj, out):
    raw_path = out / "raw.json"
    raw_path.write_text(json.dumps(raw_obj), encoding="utf-8")
    return subprocess.run([sys.executable, str(BUILD), "--raw", str(raw_path), "--out-dir", str(out)],
                          capture_output=True, text=True)


class StateBudgetBuild(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads(RAW.read_text(encoding="utf-8"))
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_published_data_builds_and_matches_checked_in_output(self):
        r = build(self.raw, self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        fresh = json.loads((self.out / "state_budget.json").read_text(encoding="utf-8"))
        published = json.loads((ROOT / "data" / "state_budget.json").read_text(encoding="utf-8"))
        self.assertEqual(fresh, published, "data/state_budget.json is out of date: rerun the build")

    def test_all_eight_jurisdictions_present_with_sources(self):
        build(self.raw, self.out)
        d = json.loads((self.out / "state_budget.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(j["id"] for j in d["jurisdictions"]), sorted(["nsw", "vic", "qld", "wa", "sa", "tas", "act", "nt"]))
        for j in d["jurisdictions"]:
            self.assertTrue(j["document"]["url"].startswith("https://"))
            for key, src in j["sources"].items():
                self.assertTrue(src.get("table"), f"{j['id']} {key} has no source table")

    def test_a_typo_in_an_operating_figure_stops_the_build(self):
        bad = copy.deepcopy(self.raw)
        bad["jurisdictions"][0]["items"]["revenue"]["values"][2] += 500
        r = build(bad, self.out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("net operating balance", r.stderr)

    def test_a_part_larger_than_its_total_stops_the_build(self):
        bad = copy.deepcopy(self.raw)
        qld = next(j for j in bad["jurisdictions"] if j["id"] == "qld")
        qld["items"]["gst"]["values"][1] = 99999
        r = build(bad, self.out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gst", r.stderr)

    def test_missing_figures_stop_the_build(self):
        bad = copy.deepcopy(self.raw)
        bad["jurisdictions"][1]["items"]["interest"]["values"][3] = None
        self.assertNotEqual(build(bad, self.out).returncode, 0)

    def test_csv_has_one_row_per_jurisdiction_item_and_year(self):
        build(self.raw, self.out)
        lines = (self.out / "state_budget.csv").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines) - 1, 8 * 13 * 5)


class ShockHistory(unittest.TestCase):
    """The ready-made shock sizes come from official history; check the build and its results."""

    @classmethod
    def setUpClass(cls):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_shock_history.py")], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.h = json.loads((ROOT / "data" / "shock_history.json").read_text(encoding="utf-8"))

    def test_every_state_has_payroll_duty_and_wage_history(self):
        for sid in ["nsw", "vic", "qld", "wa", "sa", "tas", "act", "nt"]:
            for k in ("payroll", "duty", "wages"):
                self.assertIn(k, self.h["states"][sid], f"{sid} {k}")

    def test_revenue_shocks_are_falls_and_worst_is_at_least_as_bad_as_a_bad_year(self):
        for sid, s in self.h["states"].items():
            for k in ("payroll", "duty", "royalties"):
                if k in s:
                    self.assertLessEqual(s[k]["worst"], s[k]["bad_year"], f"{sid} {k}")
                    self.assertLess(s[k]["worst"], 0, f"{sid} {k}")

    def test_known_history_is_reproduced(self):
        # The global financial crisis hit property transactions everywhere in 2008-09.
        for sid in ("nsw", "vic", "qld", "sa", "wa", "tas"):
            self.assertEqual(self.h["states"][sid]["duty"]["worst_year"], "2008-09", sid)
        self.assertEqual(self.h["national"]["gst"]["worst_year"], "2008-09")
        self.assertEqual(self.h["national"]["rates"]["worst_year"], "2022-23")

    def test_act_has_no_royalty_shock(self):
        self.assertNotIn("royalties", self.h["states"]["act"])

    def test_sensitivity_cross_check_is_included(self):
        self.assertEqual(len(self.h["sensitivities"]["rows"]), 6)


if __name__ == "__main__":
    unittest.main()
