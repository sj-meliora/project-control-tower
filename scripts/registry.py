"""워크플로 단계 정의와 프로젝트 목록을 읽고 검사한다.

검사 규칙은 DESIGN.md의 DP-2를 따른다. Python 표준 라이브러리만 사용한다(C-4).
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

# 저장소 주소: https://<호스트>/<소유자>/<저장소>.git
REPO_PATTERN = re.compile(
    r"^https://(?P<host>[A-Za-z0-9.-]+(?::\d+)?)"
    r"/(?P<owner>[A-Za-z0-9._-]+)"
    r"/(?P<name>[A-Za-z0-9._-]+)\.git$"
)
STAGE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
ICON_EXTENSIONS = (".svg", ".png", ".jpg", ".jpeg", ".webp")
PROJECT_KEYS = {"repo", "stages", "icon"}
STAGE_KEYS = {"id", "name"}


class RegistryError(Exception):
    """파일을 읽을 수 없거나 JSON으로 해석할 수 없을 때 발생한다."""


def load_json(path: Path) -> object:
    """JSON 파일을 읽는다. 같은 객체 안에 키가 중복되면 오류로 처리한다."""

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise RegistryError(f"{path}: 키 '{key}'가 중복되어 있다.")
            result[key] = value
        return result

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise RegistryError(f"{path}: 파일을 읽을 수 없다. ({error.strerror})") from error
    try:
        return json.loads(text, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as error:
        raise RegistryError(
            f"{path}: JSON 형식이 올바르지 않다. ({error.lineno}행 {error.colno}열: {error.msg})"
        ) from error


def parse_repo(repo: str) -> tuple[str, str, str] | None:
    """저장소 주소에서 (호스트, 소유자, 저장소 이름)을 추출한다. 형태가 맞지 않으면 None을 돌려준다."""
    match = REPO_PATTERN.match(repo)
    if match is None:
        return None
    return match["host"].lower(), match["owner"], match["name"]


def validate_workflow(data: object) -> list[str]:
    """단계 정의를 검사하고 오류 메시지의 목록을 돌려준다."""
    if not isinstance(data, dict) or not isinstance(data.get("stages"), list):
        return ["최상위는 'stages' 배열을 가진 객체여야 한다."]
    errors: list[str] = []
    stages = data["stages"]
    if not stages:
        errors.append("stages: 단계가 하나 이상 있어야 한다.")
    seen: set[str] = set()
    for index, stage in enumerate(stages):
        where = f"stages[{index}]"
        if not isinstance(stage, dict):
            errors.append(f"{where}: 객체여야 한다.")
            continue
        for key in sorted(set(stage) - STAGE_KEYS):
            errors.append(f"{where}: 알 수 없는 항목 '{key}'가 있다.")
        stage_id = stage.get("id")
        if not isinstance(stage_id, str) or not STAGE_ID_PATTERN.match(stage_id):
            errors.append(f"{where}.id: 영문 소문자로 시작하고 영문 소문자, 숫자, '-'로만 이루어져야 한다.")
        elif stage_id in seen:
            errors.append(f"{where}.id: 식별자 '{stage_id}'가 중복되어 있다.")
        else:
            seen.add(stage_id)
        name = stage.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}.name: 비어 있지 않은 문자열이어야 한다.")
    return errors


def stage_ids(workflow: object) -> list[str]:
    """검사를 통과한 단계 정의에서 식별자를 순서대로 돌려준다."""
    return [stage["id"] for stage in workflow["stages"]]  # type: ignore[index]


def _validate_icon(icon: object) -> str | None:
    if not isinstance(icon, str) or not icon:
        return "비어 있지 않은 문자열이어야 한다."
    if "\\" in icon or "://" in icon or icon.startswith("/"):
        return "저장소 안의 상대 경로여야 한다. 예: docs/emblem.svg"
    parts = PurePosixPath(icon).parts
    if ".." in parts or "." in parts:
        return "경로에 '.'이나 '..'을 쓸 수 없다."
    if not icon.lower().endswith(ICON_EXTENSIONS):
        return "확장자는 " + ", ".join(ICON_EXTENSIONS) + " 가운데 하나여야 한다."
    return None


def validate_projects(data: object, known_stages: list[str]) -> list[str]:
    """프로젝트 목록을 검사하고 오류 메시지의 목록을 돌려준다."""
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        return ["최상위는 'projects' 배열을 가진 객체여야 한다."]
    errors: list[str] = []
    for key in sorted(set(data) - {"projects"}):
        errors.append(f"알 수 없는 항목 '{key}'가 있다.")
    seen: dict[tuple[str, str, str], int] = {}
    for index, project in enumerate(data["projects"]):
        where = f"projects[{index}]"
        if not isinstance(project, dict):
            errors.append(f"{where}: 객체여야 한다.")
            continue
        for key in sorted(set(project) - PROJECT_KEYS):
            errors.append(f"{where}: 알 수 없는 항목 '{key}'가 있다.")

        repo = project.get("repo")
        parsed = parse_repo(repo) if isinstance(repo, str) else None
        if parsed is None:
            errors.append(
                f"{where}.repo: 'https://'로 시작하고 '.git'으로 끝나는 저장소 주소여야 한다. "
                "예: https://github.com/owner/name.git"
            )
        else:
            # 호스트, 소유자, 저장소 이름은 대소문자를 구분하지 않고 비교한다.
            identity = (parsed[0], parsed[1].lower(), parsed[2].lower())
            if identity in seen:
                errors.append(f"{where}.repo: projects[{seen[identity]}]과 같은 저장소다.")
            else:
                seen[identity] = index

        stages = project.get("stages")
        if not isinstance(stages, list) or not stages:
            errors.append(f"{where}.stages: 단계를 하나 이상 지정해야 한다.")
        else:
            listed: set[str] = set()
            for stage in stages:
                if not isinstance(stage, str) or stage not in known_stages:
                    errors.append(
                        f"{where}.stages: '{stage}'는 단계 정의에 없다. "
                        "쓸 수 있는 단계: " + ", ".join(known_stages)
                    )
                elif stage in listed:
                    errors.append(f"{where}.stages: '{stage}'가 중복되어 있다.")
                else:
                    listed.add(stage)

        if "icon" in project:
            problem = _validate_icon(project["icon"])
            if problem:
                errors.append(f"{where}.icon: {problem}")
    return errors
