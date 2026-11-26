"""프로젝트 목록 파일을 검사한다.

사용법:
    python scripts/validate_projects.py [목록 파일] [--workflow 단계 정의 파일]

목록 파일을 지정하지 않으면 projects.json을 검사한다. 오류가 있으면 오류를 출력하고
종료 코드 1로 끝난다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="프로젝트 목록 파일을 검사한다.")
    parser.add_argument("projects", nargs="?", default=str(ROOT / "projects.json"), help="검사할 목록 파일")
    parser.add_argument("--workflow", default=str(ROOT / "workflow.json"), help="단계 정의 파일")
    args = parser.parse_args(argv)

    try:
        workflow = registry.load_json(Path(args.workflow))
        projects = registry.load_json(Path(args.projects))
    except registry.RegistryError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1

    errors = [f"{args.workflow}: {message}" for message in registry.validate_workflow(workflow)]
    if not errors:
        errors = [
            f"{args.projects}: {message}"
            for message in registry.validate_projects(projects, registry.stage_ids(workflow))
        ]
    if errors:
        for message in errors:
            print(f"오류: {message}", file=sys.stderr)
        print(f"오류 {len(errors)}건이 있다.", file=sys.stderr)
        return 1

    print(f"{args.projects}: 프로젝트 {len(projects['projects'])}개를 확인했다. 오류가 없다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
