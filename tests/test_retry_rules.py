import json
import pathlib
import tempfile
import unittest

from oml_mcp.retry_rules import RetryRuleError, load_rules, lookup, rule_ids


def valid_rule(rule_id: str = "r1", **overrides):
    rule = {
        "schema_version": "oml.retry-rule.v1",
        "id": rule_id,
        "title": "test rule",
        "symptom": "test symptom",
        "layer": "exx",
        "evidence_required": ["evidence"],
        "candidate_experiments": [
            {"action": "do something", "expected_improvement": "improve"}
        ],
        "stop_condition": "stop when done",
        "sources": [{"kind": "test", "ref": "test", "accessed": "2026-10-23"}],
    }
    rule.update(overrides)
    return rule


class RetryRuleTest(unittest.TestCase):
    def test_all_rules_load_in_order(self):
        rules = load_rules()
        self.assertEqual(rule_ids(rules), tuple(f"r{index}" for index in range(1, 10)))
        for rule in rules:
            self.assertTrue(rule["symptom"])
            self.assertTrue(rule["candidate_experiments"])
            self.assertTrue(rule["sources"])
            self.assertIn(rule["layer"], {"exx", "gw", "both", "any"})
            for experiment in rule["candidate_experiments"]:
                self.assertTrue(experiment["action"])
                self.assertTrue(experiment["expected_improvement"])

    def test_lookup_finds_the_exx_fullcoul_rule(self):
        rule = lookup("r2")
        self.assertEqual(rule["layer"], "exx")
        parameters = [
            parameter
            for experiment in rule["candidate_experiments"]
            for parameter in experiment.get("parameters", [])
        ]
        self.assertIn("out_librpa_3d_coulomb_method", parameters)

    def test_unknown_rule_is_rejected(self):
        with self.assertRaises(RetryRuleError):
            lookup("r99")

    def test_invalid_layer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "bad.json").write_text(
                json.dumps(valid_rule(layer="nope")), encoding="utf-8"
            )
            with self.assertRaises(RetryRuleError):
                load_rules(root)

    def test_duplicate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "a.json").write_text(json.dumps(valid_rule("r1")), encoding="utf-8")
            (root / "b.json").write_text(json.dumps(valid_rule("r1")), encoding="utf-8")
            with self.assertRaises(RetryRuleError):
                load_rules(root)

    def test_missing_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "bad.json").write_text(
                json.dumps(valid_rule(sources=[])), encoding="utf-8"
            )
            with self.assertRaises(RetryRuleError):
                load_rules(root)


if __name__ == "__main__":
    unittest.main()
