# 4단계 실제 앱 실행·검수 안내

**최신 실행 기준:** 실제 Gmail 자동 처리와 실제 AI 모드를 사용한다. 기존 화이트톤 유지, 누적 금액 예산 통제 없음. [자동 Gmail 사용 안내](18-automatic-gmail-review.md)를 먼저 읽는다. 아래 합성/수동 모드 안내는 이전 검수 시점의 기록이다.

상태: **로컬 구축본 검수 대기 · 2026-11-02**. 설계와 화면 목업 승인을 바탕으로 실제 LangGraph·OpenAI·LangSmith·Hermes 연결을 구현했다. 5단계 정식 수용 검증과 6단계 시연은 아직 시작하지 않는다.

**현재 검수 모드 변경:** 사용자가 추가 비용 없이 진행하기를 요청해 `config/application.toml`에 `llm_mode="scripted"`, `trace_enabled=false`를 적용했다. 이 설정에서는 아래 실행·평가·진단 버튼도 외부 모델을 호출하지 않는다. 화면 흐름·승인·복구는 로컬에서 확인할 수 있고, 실제 모델 품질과 LangSmith 신규 전송 검증은 별도 사용자 승인까지 중단한다. 이미 실행 중인 앱은 종료 후 다시 실행해야 설정이 반영된다. 과거 실제 연결 결과와 기록은 그대로 보관한다.

## 처음 실행

1. 프로젝트 폴더에서 `Open-Console.cmd`를 더블클릭한다.
2. 약 1분까지 기다리면 인증된 브라우저가 열린다. 서버는 `127.0.0.1:8000`, Hermes HTTP Gateway는 `127.0.0.1:8642`에서만 접근한다.
3. **합성 테스트 메일**을 선택하고 **테스트 실행**을 누른다. 현재 설정은 scripted 합성 응답이므로 OpenAI를 호출하지 않는다. 로컬 일일 호출 상한은 UTC 날짜별 500회다. 실제 모델 토큰·비용은 미측정이며 실제 품질 평가로 해석하지 않는다.
4. 종료하려면 실행 창에서 `Ctrl+C`를 누른다. 창을 강제로 닫으면 자식 Gateway가 남을 수 있다. 원래 실행 창을 중복으로 열지 않는다.

최초 접속은 실행기가 연 탭을 사용한다. 한 번 쓰는 시작 코드는 URL fragment에서 즉시 제거되고 HttpOnly 세션으로 바뀐다. 수동으로 주소만 입력해 인증 화면이 나오면 기존 실행을 종료하고 실행기를 다시 시작한다. 비밀번호·API 키를 브라우저에 입력하지 않는다.

실행 창에 `status: failed`가 나오고 아무 키나 누르라는 문구가 표시되면 실행이 종료된 상태다. 기다려도 열리지 않는다. `HERMES_GATEWAY_PORT_IN_USE`는 8642 포트를 이전 Gateway가 사용한다는 뜻이다. 이전 실행 창에서 Ctrl+C로 종료한 뒤 다시 연다. 이전 창이 없으면 포트 소유 프로세스의 프로젝트 경로와 명령을 확인한 후 해당 Gateway만 종료한다. 다른 프로세스를 일괄 종료하지 않는다. 2026-11-02 실제 시작 실패는 이 충돌을 확인·정리해 복구했고 앱 8000 / Gateway 8642의 HTTP 200을 확인했다.

API 빌드가 없다고 나오면 프로젝트에서 다음을 실행한 뒤 실행기를 연다. 이미 현재 빌드는 준비돼 있다.

```powershell
cd frontend
npm.cmd run build:api
```

기존 승인 목업은 `frontend`에서 `npm run dev`로 실행하며 주소는 `127.0.0.1:5173`이다. **5173은 목업, 8000은 실제 API 앱**이다. 두 화면은 같은 레이아웃을 사용하지만 데이터와 저장 동작은 다르다.

## 검수 흐름

| 화면 | 확인할 내용 | 예상 결과 |
|---|---|---|
| 메일 작업실 | 합성 실행의 수신·분류·초안·Critic·검토 단계 | 동일 메일 안에서 전 과정과 원문/초안 확인 |
| 메일 작업실 | 초안 수정 → 저장 → 승인 | revision 증가, 로컬 테스트 Draft ID 표시, 자동 발송 없음 |
| 실행 감독 | 노드 선택, 태스크/메모리/입출력/이력 | 실제 이벤트 cursor에 맞춘 공개 상태, graph edge, 체크포인트 |
| 실행 감독 | 과거 시점 재생 | 당시까지의 상태만 표시. 현재 승인과 혼동하지 않음 |
| LLMOps 판단실 | 개발 회귀 평가 · 합성 2건 | 업무 graph와 별도 evaluator 호출, 점수·실패 사례·버전 기록 |
| LLMOps 판단실 | 건강 진단 갱신 | 운영 집계와 근거 ID를 사용한 가설. 규칙 판정·권한 변경 없음 |
| LLMOps 판단실 | 이벤트 전송·대사 | 현재 신규 전송 비활성. 과거 연결 기록은 유지하며, 재개 시 서버 조회까지 확인한 이벤트만 coverage에 반영 |
| LLMOps 판단실 | 8개 release gate | 표본/안전/복구 근거 부족으로 HOLD, 승격 버튼 비활성 |
| 원장·상세 화면 | run/agent/평가 사례/manifest 상세 | 실제 ID와 기록 연결, 미측정 N/A, 목업 예시와 분리 |

실제 모델은 같은 입력에서도 결과가 달라질 수 있다. Critic이 최대 2회 수정을 요청하거나 사람에게 판단을 넘기는 것은 정상적인 경로다. 실패하면 오류 유형과 원장을 보존하며, 외부 쓰기 intent가 있는 실행은 새로 저장하지 않고 대사한다.

## 실제 연결과 로컬 구현의 경계

- **실제 동작:** LangGraph 감독/전문 subgraph, 병렬 합류, 제한된 재작성, 사람 검토 interrupt/resume, OpenAI 구조화 호출, 암호화 DB·원장·outbox, Hermes command adapter, 세션·CSRF, SSE, 독립 평가·진단, LangSmith trace/feedback/native experiment.
- **합성 입력에서 로컬로 확인:** 초안 수정/승인/거절, Draft 저장 결과, 응답 유실·중복 방지·재시작·대사·하위 팀 확장·원장 실패 경계. 실제 Gmail Draft 저장 성공으로 주장하지 않는다.
- **현재 차단:** 실제 Gmail 본문의 OpenAI 전송, Gmail Draft 쓰기. 기존 OAuth는 readonly이며 앱 설정 두 정책은 false다. 발송 메서드는 Broker에 없다.
- **배포 범위:** 동일 코드·설정의 manifest와 8개 PASS를 사람 승인으로 로컬 canary 기록에 활성화하는 기능이다. 이전 manifest hash를 검사하는 rollback 경로도 있다. 다른 코드/권한으로 바꾸려면 해당 버전으로 재시작해야 한다. 외부 운영 서버/서비스 설치·자동 production 배포 adapter는 제공하지 않는다.
- **운영 인증 미완료:** 정식 holdout 300건·위험 60건·서로 다른 shadow 200건·3회 반복, release별 안전/복구/capture 검증, 비용 baseline, 운영 건강 probe. 개발 테스트를 이 증거로 대체하지 않는다.

## LLMOps 데이터와 판정

각 release는 code/schema/prompt/model/전체 실행 설정·의존성 lock hash·Hermes commit·명령 plugin hash를 고정한다. 코드나 설정이 바뀌면 새 release ID가 생기며 이전 점검 점수를 새 버전에 복사하지 않는다. 판단실에서 이전 평가를 보려면 그 평가의 release를 선택한다. 각 실행의 로컬 상세 입출력·공개 memory·수정 이력은 암호화해 저장한다. LangSmith에는 raw 메일·수신자·초안·비밀을 보내지 않고 event/run/release ID, 역할, usage, 점수, 해시 참조만 전송한다. 상세 원문은 인증된 로컬 화면에서 조회한다. 숨겨진 모델 추론은 수집하지 않는다.

새 release는 하네스 소스·prompt·schema·factory 소스·의존성 lock 원문을 암호화된 artifact로 함께 보관한다. 소스 hash가 manifest와 다르면 시작을 거부한다. 인증된 `/api/v1/releases/{releaseId}/artifact`에서 조회할 수 있다. 과거 버전에 없었던 원문을 현재 코드로 소급 생성하지 않으며, 이 자료만으로 Python 실행 환경 전체가 복원되는 것은 아니다. 평가 상세의 baseline은 해당 사례에 대응하는 이전 실행의 실제 출력이다.

LangSmith runtime project는 **`hermes-mail-dev-runtime-v2`**다. 로컬 execution ID로 metadata를 찾는다. root → agent → 이벤트/LLM span과 버전을 확인할 수 있다. 개발 중 v1 trace는 원래 프로젝트에 보존했으며 새 계측 버전으로 재대사한다. 동일 버전의 재전송은 로컬 event UUID에서 결정적으로 만든 같은 remote UUID를 사용하고 metadata의 `event_id`로 원장을 연결한다. native Eval experiment는 `hermes-mail-eval-…` 이름으로 생성하며 input/output hash와 case ID·점수로 로컬 사례를 연결한다. 네트워크나 SDK 오류 시 outbox가 남고 coverage를 100%로 표시하지 않는다. root는 사람 검토 중에는 열려 있고 실제 종료 시 한 번 닫는다. 에이전트 묶음 span과 별도로 실제 응답 지연은 LLM leaf에서 측정한다.

LLM leaf usage만 합산하며 측정 누락은 N/A다. 비용은 GPT-5.4 mini 가격 snapshot의 추정값이며 청구서와 일치한다고 보장하지 않는다. active latency는 사람 검토 대기 시간을 제외한다. 작은 표본의 p95는 성능 benchmark가 아니다.

판정 우선순위는 기술·안전 결함이면 `DEBUG_REQUIRED`, 필수 증거 미완료면 `HOLD`, 증거가 완결됐지만 품질/성능 미달이면 `IMPROVE_REQUIRED`, 모두 통과하면 `READY_FOR_APPROVAL`이다. Diagnose LLM은 원인 후보와 후속 실험만 제안한다. 승격·도구 권한 변경은 수행하지 않는다.

## 검수 후 실제 Gmail 연결 범위 확대

사용자 검수 때 별도로 진행한다. 아래는 준비된 방법이며 이번 구축에서 실행하지 않았다.

1. 실험용 Gmail에 `agent-test` 라벨을 준비하고 모델로 전송해도 되는 테스트 메일만 둔다.
2. `config/application.example.toml`을 `config/application.toml`로 복사한다. `allow_real_mail_export`의 의미는 **메일 본문을 OpenAI로 전송함에 동의**하는 것이다. 로컬 운영자가 명시적으로 true로 바꾼 뒤 서버를 재시작한다. 권한 변경은 새 release ID가 된다.
3. Gmail Draft 쓰기가 필요하면 별도 OAuth 동의를 받는다. Google의 compose scope는 발송 권한도 포함한다. 앱 Broker는 `drafts.create`만 제공한다. 이 한계를 이해한 후에만 다음을 직접 실행한다.

```powershell
.\backend\.venv\Scripts\python.exe -m mail_tools.cli gmail-auth --client-config "다운로드한 실제 JSON 파일의 전체 경로" --test-account --draft-write --acknowledge-compose-includes-send
```

4. 동의 후 `allow_gmail_draft_write=true`를 별도로 설정하고 재시작한다. 최신 스레드·승인 revision·내용/수신자 hash·유효기간을 검증한 사람 승인만 저장된다. Google 메일 도착과 쓰기 사이를 원자적으로 잠글 수는 없어, 쓰기 직전 재확인과 미확정 대사를 적용한다.

## 개발자 재현 명령

프로젝트 루트 PowerShell에서 실행한다. `.ps1` 실행 정책을 변경할 필요가 없다. API 모델 실행·평가·진단 명령은 비용이 발생할 수 있다. 앱이 실행 중이면 먼저 `Ctrl+C`로 종료한다. DB 동시 변경을 막는 단일 runtime 잠금을 사용한다.

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
.\backend\.venv\Scripts\python.exe -m mail_tools.cli run-fixture --allow-network
.\backend\.venv\Scripts\python.exe -m mail_tools.cli evaluate --allow-network
.\backend\.venv\Scripts\python.exe -m mail_tools.cli diagnose --allow-network
.\backend\.venv\Scripts\python.exe -m mail_tools.cli trace-flush --allow-network
```

프론트 폴더에서:

```powershell
npm.cmd run build:api
npx.cmd playwright test --config playwright.api.config.ts
npx.cmd playwright test
```

별도 합성 평가셋은 `mail-tools dataset-import`에 JSON 경로를 지정해 digest로 잠근 뒤 `evaluate --dataset <반환 ID> --allow-network`로 실행한다. 스키마는 `backend/src/mail_tools/app/datasets.py`의 `Corpus/Case`에 정의돼 있다. `source=synthetic`, `split=dev|holdout`, 고유 case ID·subject·body·reference·requests·risk를 사용한다. 최소 표본 미달인 holdout도 운영 증거를 충족하지 못한다. 자동으로 수백 건을 생성하거나 유료 평가를 무제한 실행하지 않았다.

## 보관과 제한

키는 Windows Credential Manager에, DB의 민감 payload와 checkpoint 상태는 `.local/application`에 암호화 저장한다. SQLite 파일 전체 암호화는 아니며 ID·시각 등의 인덱스 metadata는 남는다. 보존 기본값은 7일이며 만료 시 원문 artifact와 checkpoint를 삭제하고 hash/tombstone 감사 metadata를 유지한다. Windows 동일 사용자 권한을 가진 프로세스 전체를 격리하는 보안 경계는 아니다. LangSmith metadata 보존은 별도 클라우드 설정이다. 개인 메일을 운영에 쓰기 전에 그 정책도 검수한다.

최종 연결·실행 증거는 `docs/13-build-progress.md`, `.local/application/phase4-evidence.json`, `.local/reports/`를 참조한다. 이 문서는 구축 검수용이며 사용자의 4단계 승인이나 운영 배포 승인을 대신하지 않는다.
