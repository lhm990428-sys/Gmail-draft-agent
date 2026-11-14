# 3단계 Tool 셋업·연동

상태: **3단계 점검 후 사용자가 4단계 진행 승인 · 2026-11-02**. 아래는 셋업 당시 기록이다. 현재 구축본 상태와 실제 실행 방법은 [4단계 검수 안내](14-runtime-review.md)를 따른다.

## 확정한 선택

| 경계 | 선택 |
|---|---|
| Hermes | Nous Research Hermes Agent 안정 릴리스 v0.22.5 |
| 소스 고정 | `bf0203a794a07aac3ff764972ab9087baa4e4f4e` |
| 업무 백엔드 | 프로젝트 전용 CPython 3.12.16, `backend/.venv`, `backend/uv.lock` |
| Hermes 런타임 | 별도 CPython 3.14.10, `.local/hermes-agent/.venv`, 공식 `uv.lock` |
| LLM | 사용자 선택 OpenAI / `gpt-5.4-mini`; 역할별 품질 적합성은 아직 미평가 |
| LangSmith | 사용자 선택 US, `https://api.smith.langchain.com`, dev setup project |
| Gmail | Google Desktop OAuth, 테스트 계정, 초기 `gmail.readonly`만 |
| Secret | 명시적으로 Windows Credential Manager, 평문 fallback 없음 |

Hermes upstream의 현재 지원 런타임은 Python 3.14다. 기존 설계의 업무 백엔드 Python 3.12를 바꾸지 않고 프로세스·환경을 분리한다. CLI가 표시하는 버전/날짜와 GitHub release 날짜는 다를 수 있으므로 실제 checkout commit을 설치 식별자로 사용한다. 기본 패키지만으로 HTTP Gateway의 `aiohttp`가 설치되지 않아 공식 `messaging` extra를 추가했다. SDK 설치는 플랫폼 활성화나 메시지 전송이 아니다.

## 이번 단계의 코드 범위

- `backend/pyproject.toml` / `uv.lock`: FastAPI, LangGraph, SQLite checkpointer, LangSmith, LangChain OpenAI adapter, OpenAI SDK, SQLAlchemy/Alembic, Google SDK, keyring의 실제 설치 버전 고정.
- `config/integrations.example.toml`: 비밀 없는 설정 계약. 사용자 선택은 무시 파일 `config/local.toml`에 저장.
- `tools/setup.ps1`: 프로젝트 내부 Python/uv/SDK 재현 설치. 사용자 전역 PATH 변경·자동 서비스 등록·계정 로그인을 하지 않는다. 최초 작업에서 발견한 공유 Python은 bootstrap에만 사용했으며 실제 업무 환경은 프로젝트 Python이다.
- `tools/tool.ps1`: 로컬 점검·숨김 키 저장·명시적 외부 probe 실행.
- `backend/src/mail_tools`: 설정 검증, 보안 저장소, 독립 SDK smoke, 제한된 합성 연결 점검. 업무 에이전트나 콘솔 API 서버를 구현한 것이 아니다.

현재 프론트엔드는 승인된 목업 그대로 `VITE_DATA_MODE=mock`다. `/api/v1` 업무 API·SSE·실제 공개 메모리·상태 원장은 4단계 대상이다. `VITE_DATA_MODE=api`로 전환하면 아직 업무 서버가 없으므로 동작하지 않는다.

## 검증과 증거의 구분

| 항목 | 확인 범위 | 아직 증명하지 않은 것 |
|---|---|---|
| 설치 | lockfile resolve/sync, 패키지 import, Hermes CLI 버전 | 모델 계정 접근·실제 업무 처리 |
| 오프라인 smoke | 실제 LangGraph compile/invoke/interrupt, SQLite 파일 close/reopen 후 resume, SQLAlchemy WAL transaction | 업무 task DAG·Supervisor·정책·durable outbox |
| Secret roundtrip | 임의 문자열을 WinVault 저장·조회 후 삭제 | 사용자 실제 키의 권한/결제 상태 |
| Hermes probe | 임시 프로필 loopback `/health`, 무인증 `/v1/models` 거부, 임시 키로 허용, 종료 | 업무 서비스로 명령 전달·task 이벤트 projection·Gmail Broker 격리 |
| OpenAI probe | 고정 합성 입력 1회, usage/latency/request ID 수신 | 역할별 모델 품질·예산 gate·실제 메일 생성 |
| LangSmith probe | 합성 trace 쓰기/조회 + 숫자 feedback 쓰기/조회 | holdout Eval/Experiment, 전체 이벤트 대사, Observe/Diagnose/Release |
| Gmail probe | readonly OAuth와 `labels.list` 메타데이터 응답 | thread 읽기·메일 분류·Draft 생성·발송 차단 Broker |

`doctor`는 네트워크를 호출하지 않으며 각 연결 상태를 `not_probed`로 표시한다. 과거 probe 결과와 혼동하지 않는다. `present_not_validated`도 연결 성공이 아니다. SDK만 설치해 놓고 LangSmith 중심 LLMOps가 완성됐다고 표현하지 않는다.

실제 점검 결과는 비밀 없는 `.local/reports/*.json`에 명령·확인 시각과 함께 저장한다. `smoke.json`, `vault-probe.json`, `hermes-probe.json`, `probe-openai.json`, `probe-langsmith.json`, `probe-gmail.json`을 구분한다. 해당 probe가 아직 실행되지 않았다면 파일이 없고 연결 성공으로 인정하지 않는다. 실패 후 이전 성공 기록이 남을 수 있으므로 항상 최신 명령 결과·확인 시각을 기준으로 검수한다.

## 실행

```powershell
# 재설치가 필요할 때만. 현재 머신에서는 설치를 수행했다.
.\tools\setup.ps1 -IncludeHermes

.\tools\tool.ps1 doctor
.\tools\tool.ps1 smoke
.\tools\tool.ps1 vault-probe
.\tools\tool.ps1 hermes-probe
```

Hermes probe는 provider/Gmail/LangSmith 자격증명을 전달하지 않고 임시 API key를 메모리에서 생성한다. 모델 요청·agent run은 만들지 않는다. 항상 loopback으로 바인딩하고, 본인이 생성한 프로세스 트리만 종료한다. Windows의 Hermes 파일 보호로 임시 프로필 삭제가 실패할 수 있어 `.local/gateway-probe-*`를 합성 점검 잔여물로 보관한다. 여기에 실제 키·메일을 넣지 않는다. Gateway 상시 실행, 예약 작업, 외부 노출, CORS 확장은 하지 않는다.

처음 계정·키를 만드는 절차는 [계정 설정 안내](11-account-setup-guide.md)에 있다. 키는 파일·CLI 인자·프론트 변수에 쓰지 않고 숨김 prompt로 입력한다. 저장소 접근이 막힌 실행 sandbox에서는 `vault_unavailable`일 수 있으므로 본인 PowerShell에서 확인한다. 본인 사용자 권한의 저장/조회/삭제 synthetic roundtrip을 별도로 검증했다.

## 3단계 완료 조건

- [x] 목업 승인과 공급자/리전/Hermes 제품 확정
- [x] 프로젝트 독립 Python·SDK 환경 설치와 lockfile 고정
- [x] LangGraph/SQLite 재개 호환성 확인
- [x] Windows 비밀 저장소 합성 roundtrip 확인
- [x] Hermes HTTP Gateway liveness/auth 확인 — `/health` 정상, 무인증 401, 임시 인증키 200, 점검 프로세스 종료
- [x] 사용자 OpenAI 키 발급·보안 저장, 합성 모델 요청 성공 (2026-11-02, 충전 후 재점검)
- [x] 사용자 LangSmith 계정·키 발급·보안 저장, 합성 trace/feedback 대사 성공 (2026-11-02)
- [x] 사용자 Google Cloud OAuth 설정, 테스트 계정 readonly 인증·메타데이터 조회 성공 (2026-11-02)
- [x] 사용자가 점검 이후 4단계 구축 진행 승인

현재 실제 API 키·OAuth 인증이 없으면 로컬 준비까지만 완료할 수 있다. 인증 미완료를 숨기거나 가짜 연결 상태로 바꾸지 않는다.

2026-11-02 갱신: Gmail·LangSmith 실제 연결은 통과했다. OpenAI는 현재 저장 키로 제한된 합성 요청 2회를 시도했으나 HTTP 429 / RateLimitError로 모두 거부되어 모델 연결 성공을 확인하지 못했다. 잔액 부족과 순간 호출 제한을 구분하는 세부 오류 코드는 응답에서 확인하지 못했으므로 결제·크레딧·프로젝트 한도를 확인해야 한다. 계정 상태 변경 전 추가 재시도는 하지 않았다. [실제 점검 결과](12-integration-check.md)

후속 결과: 사용자가 충전 완료를 알린 뒤 합성 요청 1회로 재점검해 OpenAI 연결도 통과했다. provider reported model `gpt-5.4-mini-2026-03-17`, 입력 17 / 출력 5토큰, 지연 5,203ms. 비용은 API 응답에서 확인하지 못해 null로 유지했다. 3단계 점검 증거가 준비됐으며 사용자 검수·4단계 승인만 대기한다.

진단 코드 보완 후 backend 테스트 9건이 통과했다. 실패 report에도 확인 시각·HTTP 상태·허용 목록의 오류 코드만 저장하고 raw SDK 오류/헤더/본문은 출력하지 않는다. 현재 CLI는 실패 시에도 같은 probe report를 갱신해 이전 성공을 최신 결과로 오인하지 않도록 했다.

2026-11-01 로컬 검증: backend 단위/경계 테스트 8건 통과, PowerShell 두 스크립트 구문 오류 없음, wrapper를 통한 offline smoke 통과, Windows Vault roundtrip 통과, Hermes HTTP probe 통과. OpenAI endpoint 고정과 환경변수에 의한 LangSmith 다중 전송 거부도 테스트했다. OpenAI/LangSmith/Gmail 실제 계정 연결은 아직 실행하지 않았다. 화면 소스를 수정하지 않아 프론트 회귀 테스트는 이번 작업에서 다시 실행하지 않았다.

## 4단계로 넘길 계약

1. Hermes는 외부 입력 gateway, LangGraph는 업무 Supervisor·전문 subgraph의 실제 실행 주체다. Hermes의 별도 자율 에이전트가 업무 graph나 사람 승인 경로를 우회하지 않도록 application command adapter와 권한 계약을 구현한다.
2. 백엔드 loopback auth/session/CSRF, 기존 REST DTO, cursor 기반 SSE, 공개 메모리 redaction을 구축한다.
3. OAuth token은 Broker만 사용한다. keyring은 OS 사용자 단위 보호이며 동일 사용자 프로세스의 강제 격리가 아니다. Hermes에 범용 실행 권한을 부여한 채 keyring 분리만으로 안전하다고 주장하지 않는다.
4. thread 최신성·승인 해시·durable write intent·uncertain 대사와 Draft-only allowlist를 서버에서 구현한 뒤 compose 동의를 별도로 검수한다. 이 단계에는 Draft 쓰기 probe를 제공하지 않는다.
5. 로컬 ledger/outbox → LangSmith mapping/대사, 잠긴 Eval 데이터셋·점수, leaf token/cost/latency, health probe, Diagnose, 8개 Release gate를 하나의 release ID에 연결한다. 합성 연결 점수는 업무 품질 점수로 사용하지 않는다.

## 공식 근거

- [Hermes v0.22.5 릴리스](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.5)
- [Hermes Windows 네이티브 지원](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native)
- [고정한 Hermes 설치 요구사항](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/pyproject.toml)
- [고정한 API Server 문서](https://github.com/NousResearch/hermes-agent/blob/bf0203a794a07aac3ff764972ab9087baa4e4f4e/website/docs/user-guide/features/api-server.md)
- [LangGraph 설치와 provider 분리](https://docs.langchain.com/oss/python/langgraph/install)
- [LangSmith 민감 입력/출력 보호](https://docs.langchain.com/langsmith/mask-inputs-outputs)

추가 스킬은 설치하지 않았다. 이번 작업은 승인된 스택의 공식 SDK와 문서를 기반으로 진행했다.
