import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aggregate  # noqa: E402

WORKFLOW = {"stages": [{"id": "design", "name": "설계"}, {"id": "verify", "name": "검증"}]}
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
MILESTONES = [
    {"number": 3, "title": "마감일 없음", "state": "open", "due_on": None, "created_at": "2026-01-03T00:00:00Z", "open_issues": 5, "closed_issues": 0},
    {"number": 2, "title": "둘째", "state": "open", "due_on": "2026-12-05T08:00:00Z", "created_at": "2026-01-02T00:00:00Z", "open_issues": 3, "closed_issues": 5},
    {"number": 1, "title": "첫째", "state": "closed", "due_on": "2026-11-20T08:00:00Z", "created_at": "2026-01-01T00:00:00Z", "open_issues": 0, "closed_issues": 9},
]


class FakeGitHub(BaseHTTPRequestHandler):
    """집계 스크립트가 호출하는 API만 흉내 내는 서버."""

    requests: list = []
    required_token = "secret-token"

    def log_message(self, *args):
        pass

    def reply(self, status, body, headers=None, content_type="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        type(self).requests.append((self.path, self.headers.get("Authorization"), self.headers.get("Accept")))
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        origin = f"http://{self.headers['Host']}"
        if url.path.startswith("/repos/team/private") and self.headers.get("Authorization") != f"Bearer {self.required_token}":
            return self.reply(401, {"message": "Bad credentials"})
        if url.path == "/repos/team/missing":
            return self.reply(404, {"message": "Not Found"})
        if url.path in ("/repos/team/tool", "/repos/team/private"):
            return self.reply(200, {"name": "tool", "description": "예시 도구", "pushed_at": "2026-11-25T02:43:18Z", "archived": False, "open_issues_count": 6})
        if url.path.endswith("/pulls"):
            # 열린 PR이 두 개인 상황: 한 쪽에 하나씩이면 마지막 쪽은 2쪽이다.
            link = f'<{origin}{url.path}?state=open&per_page=1&page=2>; rel="next", <{origin}{url.path}?state=open&per_page=1&page=2>; rel="last"'
            return self.reply(200, [{"number": 10}], {"Link": link})
        if url.path.endswith("/milestones"):
            if query.get("page") == ["2"]:
                return self.reply(200, MILESTONES[2:])
            link = f'<{origin}{url.path}?state=all&per_page=100&page=2>; rel="next"'
            return self.reply(200, MILESTONES[:2], {"Link": link})
        if url.path.endswith("/contents/docs/emblem.svg"):
            return self.reply(200, SVG, content_type="image/svg+xml")
        return self.reply(404, {"message": "Not Found"})


class AggregateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
        cls.port = cls.server.server_address[1]
        cls.host = f"127.0.0.1:{cls.port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeGitHub.requests = []
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "data" / "status.json"
        self.hosts = {self.host: {"api": f"http://{self.host}", "token_env": "TEST_TOKEN"}}

    def repo(self, name):
        return f"https://{self.host}/team/{name}.git"

    def run_aggregate(self, projects, environ=None, hosts=None):
        return aggregate.aggregate(
            WORKFLOW,
            {"projects": projects},
            self.hosts if hosts is None else hosts,
            self.output,
            now=datetime(2026, 11, 26, 15, 4, tzinfo=timezone.utc),
            environ={"TEST_TOKEN": "secret-token"} if environ is None else environ,
        )

    def test_collects_issues_roadmap_and_icon(self):
        status = self.run_aggregate([{"repo": self.repo("tool"), "stages": ["design", "verify"], "icon": "docs/emblem.svg"}])
        self.assertEqual(status["aggregatedAt"], "2026-11-26T15:04:00Z")
        self.assertEqual(status["stages"], WORKFLOW["stages"])
        project = status["projects"][0]
        self.assertIsNone(project["error"])
        self.assertEqual(project["name"], "tool")
        self.assertEqual(project["description"], "예시 도구")
        self.assertEqual(project["url"], f"https://{self.host}/team/tool")
        self.assertEqual(project["stages"], ["design", "verify"])
        # 저장소의 열린 이슈 6건에서 열린 PR 2건을 뺀다.
        self.assertEqual(project["openIssues"], 4)
        self.assertEqual([m["title"] for m in project["roadmap"]], ["첫째", "둘째", "마감일 없음"])
        self.assertEqual(project["roadmap"][1], {"title": "둘째", "state": "open", "dueOn": "2026-12-05", "open": 3, "closed": 5})
        self.assertIsNone(project["roadmap"][2]["dueOn"])
        icon = self.output.parent.parent / project["icon"]
        self.assertEqual(icon.read_bytes(), SVG)
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8")), status)

    def test_sends_token_from_environment(self):
        status = self.run_aggregate([{"repo": self.repo("private"), "stages": ["verify"]}])
        self.assertIsNone(status["projects"][0]["error"])
        self.assertTrue(all(auth == "Bearer secret-token" for _, auth, _ in FakeGitHub.requests))

    def test_missing_token_variable_is_reported_per_project(self):
        status = self.run_aggregate([{"repo": self.repo("private"), "stages": ["verify"]}], environ={})
        self.assertIn("TEST_TOKEN", status["projects"][0]["error"])
        self.assertEqual(FakeGitHub.requests, [])

    def test_no_token_is_sent_when_not_configured(self):
        hosts = {self.host: {"api": f"http://{self.host}"}}
        status = self.run_aggregate([{"repo": self.repo("tool"), "stages": ["design"]}, {"repo": self.repo("private"), "stages": ["design"]}], hosts=hosts)
        self.assertIsNone(status["projects"][0]["error"])
        self.assertIn("401", status["projects"][1]["error"])
        self.assertTrue(all(auth is None for _, auth, _ in FakeGitHub.requests))

    def test_one_failure_does_not_stop_the_others(self):
        status = self.run_aggregate([{"repo": self.repo("missing"), "stages": ["design"]}, {"repo": self.repo("tool"), "stages": ["design"]}])
        self.assertIn("404", status["projects"][0]["error"])
        self.assertEqual(status["projects"][0]["stages"], ["design"])
        self.assertIsNone(status["projects"][1]["error"])

    def test_missing_icon_keeps_the_rest(self):
        status = self.run_aggregate([{"repo": self.repo("tool"), "stages": ["design"], "icon": "docs/none.png"}])
        project = status["projects"][0]
        self.assertIsNone(project["error"])
        self.assertIsNone(project["icon"])
        self.assertIn("404", project["iconError"])

    def test_unused_icons_are_removed(self):
        icons = self.output.parent / "icons"
        icons.mkdir(parents=True)
        (icons / "old.png").write_bytes(b"x")
        self.run_aggregate([{"repo": self.repo("tool"), "stages": ["design"], "icon": "docs/emblem.svg"}])
        self.assertEqual(len(list(icons.iterdir())), 1)
        self.assertFalse((icons / "old.png").exists())

    def test_unreachable_server_is_reported(self):
        hosts = {"127.0.0.1:1": {"api": "http://127.0.0.1:1"}}
        status = self.run_aggregate([{"repo": "https://127.0.0.1:1/team/tool.git", "stages": ["design"]}], hosts=hosts)
        self.assertIn("연결할 수 없다", status["projects"][0]["error"])


class HostsTest(unittest.TestCase):
    def test_default_api_addresses(self):
        self.assertEqual(aggregate.api_base("github.com", {}), "https://api.github.com")
        self.assertEqual(aggregate.api_base("ghe.example.com", {}), "https://ghe.example.com/api/v3")
        self.assertEqual(aggregate.api_base("ghe.example.com", {"ghe.example.com": {"api": "https://ghe.example.com/custom/"}}), "https://ghe.example.com/custom")

    def test_validate_hosts(self):
        self.assertEqual(aggregate.validate_hosts({"hosts": {}}), [])
        self.assertEqual(aggregate.validate_hosts({"hosts": {"ghe.example.com": {"api": "https://ghe.example.com/api/v3", "token_env": "X"}}}), [])
        self.assertEqual(len(aggregate.validate_hosts([])), 1)
        errors = aggregate.validate_hosts({"hosts": {"a": {"api": "http://a/api", "token_env": "", "token": "secret"}, "b": 1}})
        self.assertEqual(len(errors), 4)

    def test_example_hosts_file_is_valid(self):
        data = json.loads((ROOT / "hosts.example.json").read_text(encoding="utf-8"))
        self.assertEqual(aggregate.validate_hosts(data), [])


class RoadmapTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(aggregate.build_roadmap([]), [])

    def test_no_due_dates_are_ordered_by_creation(self):
        roadmap = aggregate.build_roadmap([
            {"number": 2, "title": "b", "state": "open", "due_on": None, "created_at": "2026-02-01T00:00:00Z"},
            {"number": 1, "title": "a", "state": "open", "due_on": None, "created_at": "2026-01-01T00:00:00Z"},
        ])
        self.assertEqual([m["title"] for m in roadmap], ["a", "b"])


class CommandLineTest(unittest.TestCase):
    def test_invalid_projects_file_fails_before_any_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projects.json"
            path.write_text('{"projects": [{"repo": "x", "stages": []}]}', encoding="utf-8")
            code = aggregate.main(["--projects", str(path), "--output", str(Path(directory) / "data" / "status.json")])
            self.assertEqual(code, 1)
            self.assertFalse((Path(directory) / "data").exists())


if __name__ == "__main__":
    unittest.main()
