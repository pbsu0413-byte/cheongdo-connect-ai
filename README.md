# 🍊 청도 돌봄 도우미

복지 상담 담당자가 상담 메모를 붙여 넣으면, **개인정보를 AI에 보내기 전에 먼저 가리고**, 담당자가 확인한 뒤에만 제도 후보와 신청서 초안을 만들며, **담당자가 승인해야 결과가 확정**되는 웹 앱입니다. 로그인 없이 바로 체험할 수 있습니다.

> 이 앱은 해커톤 데모입니다. 제도 데이터와 샘플 메모는 모두 **가상**이며, 실제 자격 판정이나 실제 개인정보 처리를 하지 않습니다.

- 제품 요구사항: [PRD.md](./PRD.md) · 기술 요구사항: [TRD.md](./TRD.md)
- 배포 URL: https://cheongdo-care-pbs.azurewebsites.net (Azure App Service, Linux, Python 3.12, 일본 동부)

## 시연 순서 (약 3분)

1. 첫 화면의 **샘플 버튼**(▶)을 누릅니다. 입력 없이 마스킹 단계로 넘어갑니다.
2. 마스킹 결과에서 이름·전화·주민번호 형태·주소가 `[이름A]` 같은 표시자로 바뀐 것을 확인하고, 한계 안내를 읽습니다.
3. **확인하고 진행**을 누릅니다. 이 단계 전에는 AI를 호출하지 않습니다.
4. 제도 후보와 메모 근거를 확인하고, 후보 하나로 **초안 작성**을 누릅니다.
5. 초안을 수정하고 **승인**을 누르면 상태가 승인됨으로 바뀝니다.
6. (선택) 샘플 10번(지시문이 섞인 메모)으로 프롬프트 인젝션 방어를, 샘플 7번으로 이름 탐지의 한계(영문 이름)를 확인합니다.

AI가 연결되지 않은 환경에서는 화면에 **“AI 미연결 · 규칙 기반 대체 결과”** 배지가 표시되며, 이 결과는 AI가 만든 것이 아닙니다.

## 구조

```text
브라우저(단일 페이지) → FastAPI (화면과 API를 한 서비스로 제공)
   /api/mask → /api/match → /api/draft(/stream) → /api/review → /api/approve
        │          │              │                  │
   MaskingTool   MatchingAgent  DraftingAgent     ReviewAgent
   (규칙 기반)   └── Microsoft Agent Framework GitHubCopilotAgent ──▶ GitHub Copilot SDK
```

- **단계 강제:** `/api/mask`가 마스킹 결과의 해시를 서명한 토큰을 반환하고, `/api/match`·`/api/draft`·`/api/review`는 서명·만료·해시가 맞을 때만 모델을 호출합니다. 토큰에는 원문이나 개인정보가 들어가지 않습니다. 같은 방식으로 `/api/approve`는 초안 토큰을 요구합니다.
- **에이전트 3개:** 매칭 에이전트는 `lookup_schemes` 도구로 제도 목록을 조회하고(도구 호출), 초안 에이전트는 초안을 **스트리밍**으로 보내며, 검토 에이전트는 초안을 메모·제도 항목과 대조해 근거 없는 단정과 자격 확정 표현을 점검합니다. 각 에이전트는 시스템 지시와 메모를 분리해 전달하고(컨텍스트 처리), 출력은 서버가 다시 검증합니다. CLI의 셸·파일 도구는 허용하지 않고 `lookup_schemes`만 승인합니다.
- **개인정보:** 모델에는 마스킹된 텍스트만 전달합니다. 서버는 원문과 모델 입출력을 저장하거나 로그에 남기지 않습니다.
- **대체 경로:** 토큰 없음, 네트워크 오류, 시간 초과, 스키마 불일치 시 규칙 기반 결과를 반환하고 `is_fallback: true`로 표시합니다. 이 결과에는 AI 생성 표시가 붙지 않습니다.
- **처리 시간 표시:** 후보와 초안 화면에 서버가 측정한 처리 시간이 표시됩니다. 대기 중에는 경과 시간과 현재 단계가 보입니다.
- **모델 상태 표시:** `/api/health`는 모델을 호출하지 않으며, 첫 요청 전에는 `not_checked`, 이후에는 최근 매칭·초안·점검 요청의 성공(`last_call_success`) 또는 대체(`last_call_failed`) 결과를 반환합니다. 화면 상단에 같은 상태가 표시되며 실시간 연결 확인은 아닙니다.

## 로컬 실행

```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest              # 시험
python -m uvicorn app.main:app --port 8000
```

`http://127.0.0.1:8000`을 엽니다.

## 환경 변수

`.env.example`을 참고하세요. 로컬에서는 프로젝트 루트에 `.env` 파일을 만들면 자동으로 읽습니다(`.gitignore`로 제외되어 커밋되지 않음). 배포 환경에서는 앱 설정(환경 변수)으로만 주입합니다. 키와 토큰은 저장소에 두지 않습니다.

| 이름 | 설명 |
| ---- | ---- |
| `COPILOT_GITHUB_TOKEN` | 선택적 GitHub Copilot SDK 인증 토큰. SDK는 저장된 Copilot CLI 로그인도 사용할 수 있으며, 사용 가능한 인증이 없으면 규칙 기반 대체 결과가 표시됩니다. |
| `SIGNING_KEY` | 단계 토큰 서명 키. 미설정 시 서버 시작마다 임의 생성됩니다(인스턴스를 여러 개로 늘리면 설정 필요). |
| `COPILOT_MODEL` | (선택) 사용할 모델 |
| `COPILOT_CLI_EXTRACT_DIR` | (선택) Copilot 런타임 캐시 경로. 기본은 사용자 캐시 폴더이며 쓰기 가능해야 합니다. |
| `RATE_LIMIT_PER_MINUTE` | (선택) 클라이언트별 분당 모델 호출 수 제한, 기본 30 |
| `MAX_CONCURRENT_MODEL_CALLS` | (선택) 동시에 실행할 모델 호출 수 제한, 기본 3 |
| `AZURE_OPENAI_*` | (선택) BYOK: Azure OpenAI를 Copilot SDK의 모델 공급자로 사용 |

Copilot SDK의 런타임(약 120MB)은 Python 패키지에 포함되어 있지 않고 **첫 사용 때 GitHub Releases에서 내려받아 캐시**됩니다. 앱은 시작할 때 백그라운드로 미리 내려받습니다. 배포 환경에서는 GitHub로 나가는 네트워크 접근과 쓰기 가능한 캐시 경로가 필요합니다.

## 배포 (Azure)

`infra/deploy.ps1`로 반복 배포할 수 있습니다(리소스 그룹, App Service 계획, 웹앱, 앱 설정, 코드 배포, 헬스체크까지). 사전 조건은 Azure CLI 설치와 `az login`이며, `COPILOT_GITHUB_TOKEN` 환경 변수가 있으면 앱 설정으로 주입합니다(값은 출력하지 않음).

```powershell
$env:COPILOT_GITHUB_TOKEN = "<Copilot 권한이 있는 토큰>"   # 선택
.\infra\deploy.ps1 -Name <앱이름> -Location japaneast
```

Azure 기본 도메인(`*.azurewebsites.net`)에 App Service(Linux, Python 3.12)로 배포합니다. 시작 명령은 다음과 같습니다.

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

앱 설정(환경 변수)으로 `COPILOT_GITHUB_TOKEN`, `SIGNING_KEY`, `WEBSITES_PORT=8000`, `COPILOT_CLI_EXTRACT_DIR=/home/copilot-cli`를 주입했고, `/api/health`가 HTTP 200을 반환하는지 확인합니다. Always On을 켜 두었습니다. Copilot 런타임은 시작할 때 `/home/copilot-cli`로 내려받으며(배포 환경에서 약 30초 소요 확인), 이후 호출은 같은 캐시를 사용합니다.

## 알려진 한계

- 이름·주소 마스킹은 규칙 기반이라 놓치거나 과하게 가릴 수 있습니다. 그래서 사람이 확인하는 단계가 필수입니다.
- 질병명·소득 같은 민감 정보는 가리지 않고, 발견하면 가려지지 않는다는 경고를 보여 줍니다.
- 제도 데이터는 가상이며 실제 제도와 무관합니다. 현장 담당자 검증과 업무 시간·오류 감소의 전후 측정은 하지 않았습니다.
- 호출 제한은 인스턴스 메모리 기반이라 인스턴스를 늘리면 인스턴스별로 적용됩니다.

## 검증 기록 (2026-11-05, 배포 URL과 로컬에서 직접 실행)

- 자동 시험 40개 통과(마스킹, 단계 토큰, 대체 경로, 스트리밍, 검토, 재시도, 호출 제한, 모델 상태).
- 배포 환경에서 마스킹 → 후보 → 초안(스트리밍) → 점검 → 승인이 AI 호출로 끝까지 동작함을 확인했습니다. 후보 약 11~17초, 초안 약 17초(첫 글자 약 10초), 점검 약 10초가 걸렸습니다. 이 수치는 현재 환경의 측정값이며 사람의 수작업 시간과 비교한 값이 아닙니다.
- 지시문이 섞인 샘플(10번)을 실제 모델로 시험했을 때 존재하지 않는 제도(`S-999`)나 전체 제도 추천은 나오지 않았습니다.
