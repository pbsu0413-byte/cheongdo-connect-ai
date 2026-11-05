# 청도 돌봄 도우미 - Technical requirements document

## Document control

| Field | Value |
| ----- | ----- |
| Version | 0.2 |
| Status | Draft |
| Owner | 팀 「우리가남남이가」 |
| Last updated | 2026-11-05 |
| PRD baseline | [PRD.md](./PRD.md) v0.2 (Draft), 2026-11-05 확인 |
| Release scope | 2026-11-05 대회 제출용 데모 |
| Sign-off | 없음 |

## 1. Purpose and PRD relationship

이 문서는 PRD의 FR-001~FR-006과 NFR-001~NFR-007을 검증 가능한 기술 요구사항으로 옮긴다. 제품 의도와 범위는 PRD가 기준이다. 상세 설계는 이 문서에 쓰지 않는다.

**차단 항목:** Q-003(Copilot SDK 서버 인증·실행 방식)과 Q-001(도구 사용 범위 확인)은 [6장](#6-risks-and-unresolved-decisions)에 있다.

## 2. Technical scope and system context

- **구성 요소:** 브라우저 화면, 서버 API, 마스킹 도구, 단계 제어기, 제도 매칭 에이전트, 신청서 초안 에이전트, 가상 제도 데이터.
- **외부 연동:** GitHub Copilot SDK(모델 연결), Microsoft Agent Framework(에이전트 구성).
- **데이터:** 가상 제도 JSON(읽기 전용). 영구 저장소 없음.
- **기술 선택(제안):** 서버는 Python 단일 웹 서비스로 두고 정적 화면을 함께 제공한다. 이는 팀 제안이며 아직 확정이 아니다.

## 3. Constraints, dependencies, and coverage

| ID | 제약·의존성 | 출처·상태 | 영향 |
| -- | ----------- | --------- | ---- |
| CD-001 | GitHub Copilot SDK와 Microsoft Agent Framework를 핵심 경로에서 사용해야 한다 | 대회 평가 기준, 확인 | 모델·에이전트 설계 |
| CD-002 | 앱은 Azure 기본 도메인(`*.azurewebsites.net`, `*.azurecontainerapps.io`, `*.azurestaticapps.net`)에 배포해야 한다 | 대회 제출 안내, 확인 | 배포 대상 |
| CD-003 | 로그인 없이 핵심 기능을 사용할 수 있어야 한다 | 대회 제출 안내, 확인 | 인증 없음 |
| CD-004 | 저장소는 공개이며 비밀 정보를 포함하지 않아야 한다 | 대회 제출 안내, 확인 | 환경변수 사용 |
| CD-005 | Copilot SDK의 서버 인증·실행 방식 | 미확인 (Q-003) | 구조가 바뀔 수 있음 |

### Coverage disposition

| 영역 | 상태 | 근거 |
| ---- | ---- | ---- |
| 기능 동작 | Applicable | TR-F-001~005 |
| 데이터 | Applicable | TR-D-001, TR-D-002 |
| 인터페이스 | Applicable | TR-I-001 |
| 보안·개인정보 | Applicable | TR-Q-001, TR-Q-002, TR-Q-004 |
| AI·자동 판단 | Applicable | TR-F-004, TR-Q-003, TR-Q-004 |
| 접근성·반응형 | Applicable | TR-Q-005 |
| 운영·관측 | Applicable | TR-O-001 |
| 성능·용량 | Unknown | 목표값 미정 (Q-004) |

## 4. Technical requirements

### TR-F-001: 입력 처리

- Source: FR-001
- Requirement: 서버는 메모 입력을 받아 빈 값, 과도하게 긴 값(상한은 구현 시 정해 문서화)을 거부해야 한다. 거부 시 오류 코드와 안내 문구를 JSON으로 반환해야 한다.
- Acceptance: 빈 입력과 상한 초과 입력이 거부되고, 정상 입력은 수락된다.
- Verification: API 호출 시험.

### TR-F-002: 마스킹 도구

- Source: FR-002, NFR-002
- Requirement: 마스킹 도구는 모델을 호출하지 않는 결정론적 함수여야 한다. 전화번호, 주민등록번호 형태, 이름, 주소를 표시자로 치환하고 종류별 치환 개수를 반환해야 한다. 원문을 복원하지 않는다.
- Acceptance: 가상 샘플 10건에서 전화번호와 주민등록번호 형태는 모두 치환된다. 이름과 주소의 탐지율은 측정해 기록한다(목표값은 미정).
- Verification: 샘플 시험, 탐지율 기록.

### TR-F-003: 확인 전 모델 호출 금지

- Source: FR-002
- Requirement: 서버가 단계 순서를 강제해야 한다. `/api/mask`는 마스킹된 텍스트의 해시와 만료 시각을 서명한 토큰을 반환하고, 단계 제어기는 서명·만료·해시가 모두 맞는 요청에서만 모델을 호출해야 한다. 그렇지 않은 요청은 거부해야 한다. 토큰에는 원문이나 개인정보를 넣지 않아야 한다.
- Acceptance: 토큰 없음, 텍스트 변경, 만료 토큰 요청이 모두 거부되고 모델 호출 횟수가 0이다.
- Verification: 모델 호출을 대체한 자동 시험(`tests/test_api.py`).

### TR-F-004: 제도 매칭 에이전트

- Source: FR-003
- Requirement: 매칭 에이전트는 마스킹된 메모와 제도 데이터만 입력으로 사용해야 한다. 출력은 정해진 JSON 스키마를 따라야 하고, 서버는 데이터에 없는 제도 ID를 제거해야 한다. 자격이 확정되었다는 표현을 출력하지 않아야 한다.
- Acceptance: 응답의 모든 제도 ID가 데이터에 존재한다. 후보가 없으면 빈 목록을 반환한다.
- Verification: 존재하지 않는 제도를 유도하는 샘플 시험.

### TR-F-005: 초안 에이전트와 승인 상태

- Source: FR-004, FR-005
- Requirement: 초안 에이전트는 선택한 제도 항목과 마스킹된 메모만 사용하고, 부족한 정보를 `[확인 필요]`로 표시해야 한다. AI가 만든 결과의 응답에는 `ai_generated: true`를 포함해야 한다. 승인 요청 전 상태는 `draft`이고 승인 후 `approved`여야 하며, 승인은 초안 단계에서 발급한 서명 토큰이 있을 때만 가능해야 한다.
- Acceptance: 초안 응답에 표시가 있고 상태가 요구대로 바뀐다.
- Verification: API 호출 시험.

### TR-D-001: 가상 제도 데이터

- Source: PRD 5장
- Requirement: 제도 데이터는 8~10건의 가상 제도를 담은 읽기 전용 JSON이어야 한다. 각 항목은 ID, 이름, 대상 조건, 필요 서류를 포함해야 한다.
- Acceptance: 모든 항목이 필수 필드를 갖는다.
- Verification: 스키마 검사.

### TR-D-002: 샘플 메모

- Source: FR-001
- Requirement: 가상 샘플 메모를 3개 이상 제공해야 하고, 실제 개인정보를 포함하지 않아야 한다.
- Acceptance: 샘플이 3개 이상이고 화면에서 선택할 수 있다.
- Verification: 화면 확인.

### TR-I-001: API 목록

- Source: FR-001~FR-006
- Requirement: 서버는 다음 API를 제공해야 한다. 요청·응답은 JSON이고 오류 형식은 통일한다.

| 메서드와 경로 | 설명 |
| ------------- | ---- |
| `POST /api/mask` | 마스킹 결과와 치환 개수 반환, 모델 호출 없음 |
| `POST /api/match` | 확인 표시가 있을 때 후보 반환 |
| `POST /api/draft` | 선택한 제도의 초안 반환 |
| `POST /api/approve` | 상태를 `approved`로 변경 |
| `GET /api/health` | HTTP 200과 상태 반환 |

- Acceptance: 각 API가 설명대로 동작한다.
- Verification: API 호출 시험.

### TR-Q-001: 원문 비저장·비로깅

- Source: NFR-002
- Requirement: 서버는 메모 원문과 모델 입출력을 파일, 데이터베이스, 로그에 기록하지 않아야 한다.
- Acceptance: 시험 실행 후 로그와 저장소에서 샘플 문자열이 발견되지 않는다.
- Verification: 로그 검색, 코드 검토.

### TR-Q-002: 비밀 정보 관리

- Source: NFR-003, CD-004
- Requirement: 키와 토큰은 환경변수로만 읽어야 하고 저장소에 포함하지 않아야 한다. 예시 파일에는 자리표시자만 둔다.
- Acceptance: 저장소 검색에서 실제 키가 없다.
- Verification: 저장소 검색.

### TR-Q-003: 환각 완화

- Source: FR-003, NFR-001
- Requirement: 서버는 모델 출력의 제도 ID를 데이터와 대조해 검증해야 한다. 검증 실패는 1회 재시도 후 오류로 처리해야 한다.
- Acceptance: TR-F-004의 시험을 통과한다.
- Verification: 샘플 시험.

### TR-Q-004: 프롬프트 인젝션 방어

- Source: NFR-004
- Requirement: 시스템 지시와 메모를 분리해 전달하고, 메모를 데이터로 표시해야 한다. 메모 안의 지시문으로 출력 형식이 바뀌지 않아야 한다.
- Acceptance: "이전 지시를 무시하라"를 포함한 샘플에서 출력 스키마가 유지된다.
- Verification: 인젝션 샘플 시험.

### TR-Q-005: 접근성과 반응형

- Source: NFR-005
- Requirement: 화면은 키보드로 모든 단계를 조작할 수 있고, 모바일 폭에서 가로 스크롤 없이 사용할 수 있어야 한다.
- Acceptance: 키보드 조작과 모바일 폭에서 6단계를 완료할 수 있다.
- Verification: 수동 확인.

### TR-O-001: 헬스체크와 오류 처리

- Source: FR-006, NFR-007
- Requirement: `/api/health`는 항상 HTTP 200을 반환해야 한다. 모델 호출 실패나 시간 초과 시 서버는 규칙 기반 대체 결과를 반환하고 응답에 `is_fallback: true`와 `ai_generated: false`를 포함해야 하며, 화면은 이를 "AI 미연결" 배지로 표시해야 한다. 입력·서버 오류는 오류 JSON과 다시 시도 가능한 상태로 처리해야 하며, 서버 오류 화면을 노출하지 않아야 한다.
- Acceptance: 모델 호출을 실패시켜도 후보와 초안이 대체 결과로 표시되고 AI 생성 표시가 붙지 않는다.
- Verification: 실패 주입 시험, 배포 URL 호출.

## 5. Verification, acceptance, and traceability

### Product-to-technical coverage

| PRD | TRD | 상태 |
| --- | --- | ---- |
| FR-001 | TR-F-001, TR-D-002 | Covered |
| FR-002 | TR-F-002, TR-F-003 | Covered |
| FR-003 | TR-F-004, TR-D-001, TR-Q-003 | Covered |
| FR-004, FR-005 | TR-F-005 | Covered |
| FR-006 | TR-O-001 | Covered |
| NFR-001 | CD-001, TR-F-004, TR-F-005 | Gap: Copilot SDK 경로 미확인 (Q-003) |
| NFR-002 | TR-F-002, TR-Q-001 | Covered |
| NFR-003 | TR-Q-002 | Covered |
| NFR-004 | TR-Q-004 | Covered |
| NFR-005 | TR-Q-005 | Covered |
| NFR-006 | CD-003 | Covered |
| NFR-007 | CD-002, TR-O-001 | Covered |

### Release gates

1. 배포 URL에서 로그인 없이 6단계 흐름이 완료된다.
2. 확인 전 후보 요청이 거부된다.
3. 저장소 루트에 `PRD.md`와 `TRD.md`가 있고 실제 키가 없다.

## 6. Risks, unresolved decisions, and changes

| ID | 항목 | 영향 | 차단 여부 | 다음 행동 |
| -- | ---- | ---- | --------- | --------- |
| Q-001 | 문서·코드 작성에 사용할 수 있는 도구 범위 확인 | 제출 자격 | 예 | 운영진 확인 |
| Q-003 | Copilot SDK 서버 인증·실행 방식 | 필수 기술 평가 | 예 | 확인 필요 |
| Q-004 | 성능 목표와 측정 조건 | 검증 근거 | 아니오 | 미정 |

### Readiness assessment

- Status: Draft. Q-001과 Q-003이 해결되기 전에는 제출 준비 완료로 보지 않는다.
