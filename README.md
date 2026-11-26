# project-control-tower

조직에서 관리하는 도구와 프로젝트를 워크플로와 연결하여 보여주는 안내 사이트의 저장소다.

## 목적

누구나 다음 내용을 파악할 수 있게 한다.

- 어떤 도구와 프로젝트가 있는가
- 각 도구와 프로젝트가 어떻게 운영되고 있는가
- 각 도구와 프로젝트에 어떻게 참여할 수 있는가

## 현재 상태

등록 목록의 검사와 집계 스크립트까지 구현했다. 대시보드 화면은 아직 구현하지 않았다. 요구사항은 [`REQUIREMENT.md`](REQUIREMENT.md)에, 설계 결정은 [`DESIGN.md`](DESIGN.md)에 기록한다.

## 프로젝트 등록

프로젝트는 목록 파일 `projects.json`에 항목을 추가하는 PR로 등록한다. 형식은 [`projects.example.json`](projects.example.json)을 따른다.

```json
{
  "repo": "https://github.com/owner/name.git",
  "stages": ["design", "verify"],
  "icon": "docs/emblem.svg"
}
```

- `repo`: 저장소 주소. `https://`로 시작하고 `.git`으로 끝나야 한다.
- `stages`: 관련된 워크플로 단계. 하나 이상 적는다. 쓸 수 있는 값은 [`workflow.json`](workflow.json)에 정의되어 있다.
- `icon`: 선택 항목. 프로젝트에 엠블럼이 있으면 저장소 안에서의 경로를 적는다.

PR을 올리기 전에 다음 명령으로 목록을 검사할 수 있다.

```
python scripts/validate_projects.py projects.json
```

## 집계

다음 명령은 `projects.json`에 등록된 프로젝트의 정보를 GitHub API에서 읽어 `data/status.json`을 만든다.

```
python scripts/aggregate.py
```

- 토큰이 필요한 호스트는 `hosts.json`에 토큰을 담은 환경 변수의 이름을 적는다. 형식은 [`hosts.example.json`](hosts.example.json)을 따른다. 토큰의 값은 파일에 적지 않는다.
- 집계에 실패한 프로젝트가 있어도 나머지 프로젝트는 집계한다. 실패한 프로젝트가 하나라도 있을 때 종료 코드 1로 끝내려면 `--strict`를 붙인다.
- 예시 목록으로 시험하려면 `--projects projects.example.json --output <임의의 경로>`를 지정한다.

## 기여

변경은 브랜치에서 작업하고 PR로 반영한다. PR 제목과 커밋 메시지에 적용하는 규칙은 [`CLAUDE.md`](CLAUDE.md)의 'PR 규칙'에 정리되어 있다.
