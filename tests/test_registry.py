import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import registry  # noqa: E402
import validate_projects  # noqa: E402

STAGES = ["requirements", "design", "implement", "verify", "apply"]
REPO = "https://github.com/owner/name.git"


def projects(*items):
    return {"projects": list(items)}


class ValidateProjectsTest(unittest.TestCase):
    def check(self, data):
        return registry.validate_projects(data, STAGES)

    def test_valid_entry_has_no_errors(self):
        self.assertEqual(self.check(projects({"repo": REPO, "stages": ["design", "verify"], "icon": "docs/emblem.svg"})), [])

    def test_empty_list_is_valid(self):
        self.assertEqual(self.check(projects()), [])

    def test_top_level_must_have_projects_array(self):
        self.assertEqual(len(self.check([])), 1)
        self.assertEqual(len(self.check({"projects": {}})), 1)

    def test_repo_must_be_https_and_end_with_git(self):
        for repo in [
            "http://github.com/owner/name.git",
            "git@github.com:owner/name.git",
            "https://github.com/owner/name",
            "https://github.com/owner/name.git/",
            "https://github.com/name.git",
            "https://github.com/owner/sub/name.git",
            42,
            None,
        ]:
            with self.subTest(repo=repo):
                errors = self.check(projects({"repo": repo, "stages": ["design"]}))
                self.assertEqual(len(errors), 1)
                self.assertIn("projects[0].repo", errors[0])

    def test_host_with_port_is_accepted(self):
        self.assertEqual(self.check(projects({"repo": "https://ghe.example.com:8443/team/tool.git", "stages": ["apply"]})), [])

    def test_stages_must_not_be_empty(self):
        for stages in [[], None, "design"]:
            with self.subTest(stages=stages):
                errors = self.check(projects({"repo": REPO, "stages": stages}))
                self.assertEqual(len(errors), 1)
                self.assertIn("하나 이상", errors[0])

    def test_missing_stages_is_an_error(self):
        self.assertEqual(len(self.check(projects({"repo": REPO}))), 1)

    def test_unknown_stage_is_an_error(self):
        errors = self.check(projects({"repo": REPO, "stages": ["design", "deploy"]}))
        self.assertEqual(len(errors), 1)
        self.assertIn("'deploy'", errors[0])

    def test_repeated_stage_is_an_error(self):
        errors = self.check(projects({"repo": REPO, "stages": ["design", "design"]}))
        self.assertEqual(len(errors), 1)
        self.assertIn("중복", errors[0])

    def test_duplicate_repo_is_an_error_ignoring_case(self):
        errors = self.check(
            projects(
                {"repo": REPO, "stages": ["design"]},
                {"repo": "https://GitHub.com/Owner/Name.git", "stages": ["verify"]},
            )
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("projects[1].repo", errors[0])

    def test_same_name_on_different_hosts_is_not_a_duplicate(self):
        self.assertEqual(
            self.check(
                projects(
                    {"repo": REPO, "stages": ["design"]},
                    {"repo": "https://ghe.example.com/owner/name.git", "stages": ["design"]},
                )
            ),
            [],
        )

    def test_unknown_key_is_an_error(self):
        errors = self.check(projects({"repo": REPO, "stages": ["design"], "name": "x"}))
        self.assertEqual(len(errors), 1)
        self.assertIn("'name'", errors[0])

    def test_icon_must_be_a_relative_image_path(self):
        for icon in ["", "/abs/emblem.svg", "../emblem.svg", "docs/../emblem.svg", "https://example.com/a.svg", "docs\\emblem.svg", "docs/emblem.txt", 3]:
            with self.subTest(icon=icon):
                errors = self.check(projects({"repo": REPO, "stages": ["design"], "icon": icon}))
                self.assertEqual(len(errors), 1)
                self.assertIn("projects[0].icon", errors[0])

    def test_every_problem_is_reported(self):
        errors = self.check(projects({"repo": "x", "stages": []}, "not an object"))
        self.assertEqual(len(errors), 3)


class ValidateWorkflowTest(unittest.TestCase):
    def test_repository_workflow_is_valid(self):
        workflow = registry.load_json(ROOT / "workflow.json")
        self.assertEqual(registry.validate_workflow(workflow), [])
        self.assertEqual(registry.stage_ids(workflow), STAGES)

    def test_duplicate_or_malformed_ids_are_errors(self):
        errors = registry.validate_workflow(
            {"stages": [{"id": "design", "name": "설계"}, {"id": "design", "name": "설계"}, {"id": "Design", "name": ""}]}
        )
        self.assertEqual(len(errors), 3)

    def test_stages_must_exist(self):
        self.assertEqual(len(registry.validate_workflow({"stages": []})), 1)
        self.assertEqual(len(registry.validate_workflow({})), 1)


class ParseRepoTest(unittest.TestCase):
    def test_extracts_host_owner_and_name(self):
        self.assertEqual(registry.parse_repo("https://GHE.example.com/team/my.tool.git"), ("ghe.example.com", "team", "my.tool"))

    def test_returns_none_for_other_forms(self):
        self.assertIsNone(registry.parse_repo("https://github.com/owner/name"))


class CommandLineTest(unittest.TestCase):
    def run_cli(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projects.json"
            path.write_text(content, encoding="utf-8")
            return validate_projects.main([str(path)])

    def test_example_file_passes(self):
        self.assertEqual(validate_projects.main([str(ROOT / "projects.example.json")]), 0)

    def test_invalid_entry_fails(self):
        self.assertEqual(self.run_cli(json.dumps(projects({"repo": REPO, "stages": []}))), 1)

    def test_broken_json_fails(self):
        self.assertEqual(self.run_cli('{"projects": [,]}'), 1)

    def test_duplicate_key_fails(self):
        self.assertEqual(self.run_cli('{"projects": [], "projects": []}'), 1)

    def test_missing_file_fails(self):
        self.assertEqual(validate_projects.main([str(ROOT / "no-such-file.json")]), 1)


if __name__ == "__main__":
    unittest.main()
