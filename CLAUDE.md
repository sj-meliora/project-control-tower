# Project Control Tower

조직에서 관리하는 도구와 프로젝트를 워크플로와 연결하여 보여주고, 각 도구와 프로젝트의 운영 현황과 참여 방법을 안내하는 사이트를 만드는 프로젝트다. 이 저장소는 github.com에서 개발한 뒤 사내 GHE로 반입하여 운영하며, 사이트는 사내 GHE의 GitHub Pages로 게시한다. 사내의 정보는 이 저장소에 넣지 않는다.

## 현재 상태

요구사항과 설계 결정을 정리했고, 구현을 시작한 단계다. 등록 목록의 검사와 집계 스크립트까지 구현했으며, 대시보드 화면과 GitHub Actions 워크플로는 아직 구현하지 않았다.

- `REQUIREMENT.md`: 요구사항과 제약. 이 프로젝트가 무엇을 해야 하는지는 이 문서를 기준으로 판단한다.
- `DESIGN.md`: 설계 결정(DP). 결정된 내용과 미결 사항을 DP 단위로 기록한다.
- `workflow.json`: 워크플로 단계 정의.
- `projects.example.json`: 프로젝트 목록의 예시. 실제 목록인 `projects.json`은 사내에서 만들며, 이 저장소에는 넣지 않는다.
- `scripts/registry.py`: 단계 정의와 프로젝트 목록을 읽고 검사하는 함수. `scripts/validate_projects.py`는 이를 실행하는 명령이다.
- `scripts/aggregate.py`: 등록된 프로젝트의 정보를 GitHub API에서 읽어 `data/status.json`을 만드는 집계 스크립트.
- `hosts.example.json`: 호스트 설정의 예시. 호스트마다 API 주소와 토큰을 담은 환경 변수의 이름을 적는다. 실제 설정인 `hosts.json`은 사내에서 만든다.
- `tests/`: 테스트. `python -m unittest discover -s tests`로 실행한다.
- `README.md`: 사람을 위한 안내서. 프로젝트의 목적, 현재 상태, 기여 방법을 적는다.
- `.claude/output-styles/fluent-korean.md`: 이 저장소에서 기본으로 사용하는 출력 스타일. `feature-test-map`에서 가져왔다.

## 구현 규칙

- 스크립트는 Python 표준 라이브러리만 사용한다(C-4). 운영 환경의 Python은 3.13이다.
- 파일을 읽고 쓸 때에는 인코딩을 UTF-8로 지정한다.
- `projects.json`, `hosts.json`, `data/`는 사내에서만 만들고 고치는 파일이다. github.com의 저장소에는 커밋하지 않는다(C-3, DP-1).
- 토큰의 값은 어떤 파일에도 적지 않는다. 환경 변수로만 전달한다.

## PR 규칙

- `main`에 직접 커밋하지 않는다. 변경은 브랜치에서 작업하고 PR로 반영한다. 저장소를 처음 만들 때 넣은 초기 설정 커밋만 예외다.
- PR 제목과 커밋 메시지 앞에 변경 유형을 붙인다. 예: `docs: 설계 결정 문서 추가`

| 접두사 | 쓰는 경우 |
|---|---|
| `feat:` | 기능 추가 |
| `fix:` | 오류 수정 |
| `docs:` | 문서만 변경 |
| `refactor:` | 동작을 바꾸지 않는 구조 변경 |
| `test:` | 테스트 추가·수정 |
| `chore:` | 설정, 빌드 등 그 밖의 변경 |
