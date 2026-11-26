"""등록된 프로젝트의 정보를 GitHub API에서 읽어 집계 결과 파일을 만든다.

사용법:
    python scripts/aggregate.py [--projects 목록 파일] [--hosts 호스트 설정 파일]
                                [--output 결과 파일] [--strict]

집계 규칙은 DESIGN.md의 DP-3을 따른다. Python 표준 라이브러리만 사용한다(C-4).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "project-control-tower"
TIMEOUT_SECONDS = 30
ICON_MAX_BYTES = 1024 * 1024
HOST_KEYS = {"api", "token_env"}
LOCAL_HOSTS = ("localhost", "127.0.0.1")
LINK_PATTERN = re.compile(r'<([^>]+)>;\s*rel="([a-z]+)"')


class AggregateError(Exception):
    """한 프로젝트의 집계를 계속할 수 없을 때 발생한다."""


# ---------------------------------------------------------------- 호스트 설정


def validate_hosts(data: object) -> list[str]:
    """호스트 설정을 검사하고 오류 메시지의 목록을 돌려준다."""
    if not isinstance(data, dict) or not isinstance(data.get("hosts"), dict):
        return ["최상위는 'hosts' 객체를 가진 객체여야 한다."]
    errors: list[str] = []
    for host, config in data["hosts"].items():
        where = f"hosts['{host}']"
        if not isinstance(config, dict):
            errors.append(f"{where}: 객체여야 한다.")
            continue
        for key in sorted(set(config) - HOST_KEYS):
            errors.append(f"{where}: 알 수 없는 항목 '{key}'가 있다.")
        api = config.get("api")
        if api is not None:
            parsed = urllib.parse.urlsplit(api) if isinstance(api, str) else None
            secure = parsed is not None and parsed.scheme == "https"
            local = parsed is not None and parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS
            if not (secure or local):
                errors.append(f"{where}.api: 'https://'로 시작하는 주소여야 한다.")
        token_env = config.get("token_env")
        if token_env is not None and (not isinstance(token_env, str) or not token_env):
            errors.append(f"{where}.token_env: 환경 변수의 이름을 적어야 한다.")
    return errors


def api_base(host: str, hosts: dict) -> str:
    """호스트의 API 주소를 정한다. 설정에 없으면 github.com과 GHE의 기본 주소를 쓴다."""
    configured = hosts.get(host, {}).get("api")
    if configured:
        return configured.rstrip("/")
    if host == "github.com":
        return "https://api.github.com"
    return f"https://{host}/api/v3"


def token_for(host: str, hosts: dict, environ: dict | None = None) -> str | None:
    """호스트의 토큰을 환경 변수에서 읽는다. 설정에 환경 변수가 없으면 토큰 없이 요청한다."""
    environ = os.environ if environ is None else environ
    name = hosts.get(host, {}).get("token_env")
    if not name:
        return None
    token = environ.get(name, "").strip()
    if not token:
        raise AggregateError(f"환경 변수 {name}가 설정되어 있지 않다.")
    return token


# ---------------------------------------------------------------- API 호출


class Client:
    """한 호스트의 GitHub API를 호출한다."""

    def __init__(self, base: str, token: str | None):
        self.base = base
        self.token = token

    def _request(self, url: str, accept: str) -> tuple[bytes, dict]:
        headers = {"Accept": accept, "User-Agent": USER_AGENT}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read(), dict(response.headers.items())
        except urllib.error.HTTPError as error:
            reason = {
                401: "인증에 실패했다. 토큰을 확인해야 한다.",
                403: "접근이 거부되었다. 토큰의 권한이나 호출 한도를 확인해야 한다.",
                404: "찾을 수 없다. 주소가 틀렸거나 접근 권한이 없다.",
            }.get(error.code, "요청이 실패했다.")
            raise AggregateError(f"HTTP {error.code}: {reason}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise AggregateError(f"서버에 연결할 수 없다. ({reason})") from error

    def get_json(self, path: str) -> tuple[object, dict]:
        url = path if path.startswith("http") else self.base + path
        body, headers = self._request(url, "application/vnd.github+json")
        try:
            return json.loads(body.decode("utf-8")), headers
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AggregateError("API의 응답을 JSON으로 해석할 수 없다.") from error

    def get_all(self, path: str) -> list:
        """여러 쪽으로 나뉜 목록을 끝까지 읽는다."""
        items: list = []
        url: str | None = path
        while url:
            page, headers = self.get_json(url)
            if not isinstance(page, list):
                raise AggregateError("API의 응답이 목록이 아니다.")
            items.extend(page)
            url = _links(headers).get("next")
        return items

    def count(self, path: str) -> int:
        """목록의 항목 수를 센다. 한 쪽에 하나씩 요청하고 마지막 쪽의 번호를 읽는다."""
        separator = "&" if "?" in path else "?"
        page, headers = self.get_json(f"{path}{separator}per_page=1")
        last = _links(headers).get("last")
        if last:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(last).query)
            try:
                return int(query["page"][0])
            except (KeyError, ValueError, IndexError) as error:
                raise AggregateError("API의 쪽 번호를 해석할 수 없다.") from error
        return len(page) if isinstance(page, list) else 0

    def get_raw(self, path: str) -> bytes:
        body, _ = self._request(self.base + path, "application/vnd.github.raw")
        return body


def _links(headers: dict) -> dict[str, str]:
    value = next((v for k, v in headers.items() if k.lower() == "link"), "")
    return {rel: url for url, rel in LINK_PATTERN.findall(value)}


# ---------------------------------------------------------------- 집계


def build_roadmap(milestones: list) -> list[dict]:
    """마일스톤을 로드맵의 순서로 정렬한다.

    마감일이 있는 마일스톤을 마감일의 순서로 먼저 놓고, 마감일이 없는 마일스톤을
    만든 순서로 그 뒤에 놓는다.
    """

    def order(milestone: dict) -> tuple:
        due = milestone.get("due_on")
        return (due is None, due or milestone.get("created_at") or "", milestone.get("number") or 0)

    return [
        {
            "title": milestone.get("title") or "",
            "state": "closed" if milestone.get("state") == "closed" else "open",
            "dueOn": (milestone.get("due_on") or "")[:10] or None,
            "open": int(milestone.get("open_issues") or 0),
            "closed": int(milestone.get("closed_issues") or 0),
        }
        for milestone in sorted(milestones, key=order)
    ]


def icon_file_name(host: str, owner: str, name: str, icon_path: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9.-]+", "-", f"{host}--{owner}--{name}").strip("-").lower()
    return safe + Path(icon_path).suffix.lower()


def aggregate_project(project: dict, hosts: dict, icons_dir: Path, icons_url: str, environ: dict | None = None) -> dict:
    """한 프로젝트를 집계한다. 실패하면 error 항목에 이유를 적은 결과를 돌려준다."""
    host, owner, name = registry.parse_repo(project["repo"])  # 검사를 통과한 목록이므로 None이 아니다.
    result: dict = {
        "repo": project["repo"],
        "url": project["repo"][: -len(".git")],
        "host": host,
        "owner": owner,
        "name": name,
        "stages": list(project["stages"]),
        "error": None,
    }
    try:
        client = Client(api_base(host, hosts), token_for(host, hosts, environ))
        quoted = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}"
        info, _ = client.get_json(quoted)
        if not isinstance(info, dict):
            raise AggregateError("API의 응답이 객체가 아니다.")
        # 저장소의 open_issues_count에는 열린 PR이 포함되므로, 열린 PR의 수를 뺀다.
        pulls = client.count(f"{quoted}/pulls?state=open")
        milestones = client.get_all(f"{quoted}/milestones?state=all&per_page=100")
        result.update(
            {
                "name": info.get("name") or name,
                "description": info.get("description") or "",
                "pushedAt": info.get("pushed_at"),
                "archived": bool(info.get("archived")),
                "openIssues": max(0, int(info.get("open_issues_count") or 0) - pulls),
                "roadmap": build_roadmap(milestones),
                "icon": None,
            }
        )
        icon_path = project.get("icon")
        if icon_path:
            try:
                content = client.get_raw(f"{quoted}/contents/{urllib.parse.quote(icon_path)}")
                if len(content) > ICON_MAX_BYTES:
                    raise AggregateError("엠블럼 파일이 1MiB보다 크다.")
                file_name = icon_file_name(host, owner, name, icon_path)
                icons_dir.mkdir(parents=True, exist_ok=True)
                (icons_dir / file_name).write_bytes(content)
                result["icon"] = f"{icons_url}/{file_name}"
            except AggregateError as error:
                # 엠블럼을 읽지 못해도 나머지 집계 결과는 유지한다.
                result["iconError"] = str(error)
    except AggregateError as error:
        result["error"] = str(error)
    return result


def aggregate(workflow: dict, projects: dict, hosts: dict, output: Path, now: datetime | None = None, environ: dict | None = None) -> dict:
    """모든 프로젝트를 집계하여 결과 파일을 쓰고, 쓴 내용을 돌려준다."""
    now = now or datetime.now(timezone.utc)
    icons_dir = output.parent / "icons"
    icons_url = f"{output.parent.name}/icons" if output.parent.name else "icons"
    results = [aggregate_project(project, hosts, icons_dir, icons_url, environ) for project in projects["projects"]]

    # 더 이상 쓰지 않는 엠블럼 파일을 지운다.
    used = {Path(result["icon"]).name for result in results if result.get("icon")}
    if icons_dir.is_dir():
        for path in icons_dir.iterdir():
            if path.is_file() and path.name not in used:
                path.unlink()

    status = {
        "aggregatedAt": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages": workflow["stages"],
        "projects": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="등록된 프로젝트의 정보를 집계한다.")
    parser.add_argument("--projects", default=str(ROOT / "projects.json"), help="프로젝트 목록 파일")
    parser.add_argument("--workflow", default=str(ROOT / "workflow.json"), help="단계 정의 파일")
    parser.add_argument("--hosts", default=str(ROOT / "hosts.json"), help="호스트 설정 파일. 없으면 기본값을 쓴다.")
    parser.add_argument("--output", default=str(ROOT / "data" / "status.json"), help="집계 결과 파일")
    parser.add_argument("--strict", action="store_true", help="집계에 실패한 프로젝트가 있으면 종료 코드 1로 끝낸다.")
    args = parser.parse_args(argv)

    try:
        workflow = registry.load_json(Path(args.workflow))
        projects = registry.load_json(Path(args.projects))
        hosts_data = registry.load_json(Path(args.hosts)) if Path(args.hosts).exists() else {"hosts": {}}
    except registry.RegistryError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1

    errors = [f"{args.workflow}: {m}" for m in registry.validate_workflow(workflow)]
    if not errors:
        errors = [f"{args.projects}: {m}" for m in registry.validate_projects(projects, registry.stage_ids(workflow))]
    errors += [f"{args.hosts}: {m}" for m in validate_hosts(hosts_data)]
    if errors:
        for message in errors:
            print(f"오류: {message}", file=sys.stderr)
        return 1

    status = aggregate(workflow, projects, hosts_data["hosts"], Path(args.output))
    failed = [p for p in status["projects"] if p["error"]]
    for project in status["projects"]:
        label = f"{project['host']}/{project['owner']}/{project['name']}"
        if project["error"]:
            print(f"실패: {label}: {project['error']}", file=sys.stderr)
        elif project.get("iconError"):
            print(f"경고: {label}: 엠블럼을 읽지 못했다. {project['iconError']}", file=sys.stderr)
    print(f"{args.output}: 프로젝트 {len(status['projects'])}개 가운데 {len(status['projects']) - len(failed)}개를 집계했다.")
    if failed and (args.strict or len(failed) == len(status["projects"])):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
